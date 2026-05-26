#!/usr/bin/env python3
"""
Re-fetchea las páginas de Letterboxd de entries cacheadas para extraer el
género y actualizar cache.json + cartelera.json. Idempotente: si la entry
ya tiene genre, la skipea.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from letterboxd import parse_film_soup  # type: ignore

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
CACHE_PATH = HERE / "data" / "cache.json"
CART_PATH = HERE / "data" / "cartelera.json"


def fetch_lb(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    return parse_film_soup(soup, url) or {}


def main():
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    targets = [(k, v) for k, v in cache.items() if v.get("url") and not v.get("genre")]
    print(f"Cache entries con LB URL: {sum(1 for v in cache.values() if v.get('url'))}")
    print(f"Falta genre: {len(targets)}")
    if not targets:
        print("Nada para backfillear")
        return

    updated, errors = 0, 0
    for i, (key, meta) in enumerate(targets, 1):
        sys.stdout.write(f"\r[{i}/{len(targets)}] {key[:60]:60}")
        sys.stdout.flush()
        try:
            new_meta = fetch_lb(meta["url"])
            if new_meta.get("genre"):
                cache[key]["genre"] = new_meta["genre"]
                # Backfilleamos otros campos también por si el cache es viejo
                for f in ("country", "year", "duration", "director", "title_en"):
                    if not cache[key].get(f) and new_meta.get(f):
                        cache[key][f] = new_meta[f]
                updated += 1
        except Exception as e:
            errors += 1
        time.sleep(0.6)  # rate limit modesto

    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n✓ Cache actualizado: {updated} genres añadidos ({errors} errores)")

    # Actualizar cartelera.json con los nuevos genres del cache
    cart = json.loads(CART_PATH.read_text(encoding="utf-8"))
    fixed = 0
    # Build title → genre lookup (uses lower-case cache keys)
    cache_lookup = {k: v.get("genre", "") for k, v in cache.items() if v.get("genre")}
    for s in cart["screenings"]:
        if s.get("genre"):
            continue
        for cand in (s.get("title_es", ""), s.get("title_en", "")):
            norm = (cand or "").lower().strip()
            if norm in cache_lookup:
                s["genre"] = cache_lookup[norm]
                fixed += 1
                break
    CART_PATH.write_text(json.dumps(cart, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ cartelera.json: {fixed} screenings con genre añadido")


if __name__ == "__main__":
    main()
