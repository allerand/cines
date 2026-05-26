#!/usr/bin/env python3
"""
Backfill de URLs de Letterboxd para entradas del cache que quedaron sin link.

Estrategia:
1. Para cada entry con url="" en data/cache.json:
2. Decide título de búsqueda priorizando:
   - original_title (si tenemos)
   - title_en
   - la key del cache (título scrapeado)
3. Hace search en letterboxd.com/search/films/QUERY/
4. Valida candidatos por año (±1) y/o director (overlap de palabras)
5. Si encuentra match, actualiza cache + cartelera.json
6. Skipea programas/sesiones/cortos (no son films individuales)

Uso: python3 scripts/backfill_letterboxd.py [--dry-run]
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
LB_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
    # NO Accept-Encoding — para que el server no envíe gzip (urllib no lo decomprime auto)
}
HERE = Path(__file__).resolve().parent.parent
CACHE_PATH = HERE / "data" / "cache.json"
CART_PATH = HERE / "data" / "cartelera.json"

# Patterns que indican que NO es un single film
SKIP_PATTERNS = [
    r"\bprograma de cortos\b",
    r"\bsesión\b", r"\bsesion\b",
    r"\bfunción especial\b", r"\bfuncion especial\b",
    r"\+",  # "X + Y" = double feature
    r"\bencuentro con\b",
    r"\bep final\b", r"\bepisodio\b",
    r"\bla mirada cinéfila\b",
]

def is_skippable(title: str) -> bool:
    t = title.lower()
    return any(re.search(p, t) for p in SKIP_PATTERNS)


def _name_overlap(a: str, b: str) -> bool:
    """¿Compartemos al menos una palabra de 4+ chars entre dos nombres?"""
    def norm_words(s):
        return set(w.lower() for w in re.findall(r"\w+", s) if len(w) >= 4)
    wa, wb = norm_words(a), norm_words(b)
    return bool(wa & wb)


def lb_search(query: str) -> list[dict]:
    """Búsqueda nativa de Letterboxd. El endpoint /search/films/Q/ devuelve 403
    pero /search/films/Q/page/1/ funciona. Devuelve candidatos en orden de
    relevancia.
    """
    url = f"https://letterboxd.com/search/films/{urllib.parse.quote(query)}/page/1/"
    req = urllib.request.Request(url, headers=LB_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    search error: {e}")
        return []

    # Cada resultado: <li> con <span class="film-title-wrapper"><a href="/film/SLUG/">TITLE</a></span>
    # seguido de <small class="metadata"><a ...>YEAR</a>
    seen = set()
    results = []
    # Pattern: link a /film/SLUG/ con título, seguido (eventualmente) por año
    pattern = re.compile(
        r'<a href="/film/([^/"]+)/[^"]*"[^>]*>([^<]+)</a>'
        r'(?:.*?<small class="metadata">.*?(\d{4})</small>)?',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(html):
        slug = m.group(1)
        if slug in seen:
            continue
        title = m.group(2).strip() if m.group(2) else ""
        year = int(m.group(3)) if m.group(3) else None
        seen.add(slug)
        results.append({
            "slug": slug,
            "title": title,
            "year": year,
            "url": f"https://letterboxd.com/film/{slug}/",
        })
        if len(results) >= 8:
            break
    return results


def lb_film_details(url: str) -> dict:
    """Trae año + director de una página de film para validar match."""
    req = urllib.request.Request(url, headers=LB_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return {}
    out = {}
    m = re.search(r'href="/films/year/(\d{4})/"', html)
    if m:
        out["year"] = int(m.group(1))
    # Director: <meta name="twitter:data1" content="DIRECTOR NAME">
    m = re.search(r'<meta name="twitter:data1" content="([^"]+)"', html)
    if m:
        out["director"] = m.group(1)
    return out


def find_match(meta: dict, key: str, verbose=True) -> str:
    """Intenta varias queries y devuelve URL si encuentra match válido."""
    # Candidate query strings (en orden de preferencia)
    queries = []
    if meta.get("original_title"):
        queries.append(meta["original_title"])
    if meta.get("title_en") and meta["title_en"] not in queries:
        queries.append(meta["title_en"])
    if key not in [q.lower() for q in queries]:
        queries.append(key)

    hint_year = meta.get("year")
    hint_director = meta.get("director", "")

    for q in queries:
        if verbose:
            print(f"    ddg: {q!r}")
        results = lb_search(q)
        if not results:
            continue

        # Validamos cada candidato consultando su film page para year+director
        for r in results[:3]:
            details = lb_film_details(r["url"])
            time.sleep(0.5)
            d_year = details.get("year")
            d_dir = details.get("director", "")
            year_ok = (not hint_year) or (d_year and abs(int(d_year) - int(hint_year)) <= 1)
            dir_ok = (not hint_director) or (d_dir and _name_overlap(hint_director, d_dir))

            # Acepción más fuerte: ambos validan
            if hint_year and hint_director and year_ok and dir_ok:
                if verbose:
                    print(f"    ✓ match (año+dir): {r['url']} — {d_dir} ({d_year})")
                return r["url"]
            # Solo tenemos año + matchea
            if hint_year and not hint_director and year_ok:
                if verbose:
                    print(f"    ~ match (año): {r['url']} ({d_year})")
                return r["url"]
            # Solo tenemos director + matchea
            if hint_director and not hint_year and dir_ok:
                if verbose:
                    print(f"    ~ match (dir): {r['url']} — {d_dir}")
                return r["url"]

        # Sin hint validable y el primer resultado de DDG: lo tomamos como educated guess
        if not hint_year and not hint_director:
            if verbose:
                print(f"    ? top DDG (sin validar): {results[0]['url']}")
            return results[0]["url"]
        time.sleep(0.5)
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    cart = json.loads(CART_PATH.read_text(encoding="utf-8"))

    empty = [(k, v) for k, v in cache.items() if not v.get("url")]
    print(f"Total entries: {len(cache)}")
    print(f"Sin URL: {len(empty)}")

    skipped, found, missed = 0, 0, 0
    fixes = {}

    targets = empty[:args.limit] if args.limit else empty
    for i, (key, meta) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {key}")
        if is_skippable(key):
            print("    (skip — no es single film)")
            skipped += 1
            continue
        try:
            url = find_match(meta, key)
        except Exception as e:
            print(f"    ERROR: {e}")
            url = ""
        if url:
            fixes[key] = url
            found += 1
        else:
            print("    × no match")
            missed += 1
        time.sleep(0.6)  # rate limit

    print(f"\n=== Resumen ===")
    print(f"  ✓ Encontrados: {found}")
    print(f"  - Skipeados: {skipped}")
    print(f"  × Sin match:  {missed}")

    if args.dry_run:
        print("\n(dry-run — no escribimos archivos)")
        return

    if not fixes:
        print("\nNada para guardar")
        return

    # Update cache
    for k, url in fixes.items():
        cache[k]["url"] = url
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ cache.json: {len(fixes)} URLs agregadas")

    # Update cartelera.json — buscar screenings por título
    title_to_url = {}
    for k, url in fixes.items():
        title_to_url[k] = url

    cart_fixed = 0
    for s in cart["screenings"]:
        if s.get("letterboxd"):
            continue
        for candidate in (s.get("title_es", ""), s.get("title_en", "")):
            if candidate.lower() in title_to_url:
                s["letterboxd"] = title_to_url[candidate.lower()]
                cart_fixed += 1
                break
    CART_PATH.write_text(json.dumps(cart, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ cartelera.json: {cart_fixed} screenings actualizadas")


if __name__ == "__main__":
    main()
