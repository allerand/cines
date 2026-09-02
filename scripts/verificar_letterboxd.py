#!/usr/bin/env python3
"""
Busca y VERIFICA links de Letterboxd para las funciones que quedaron sin uno.

    python3 scripts/verificar_letterboxd.py                # todas las que faltan
    python3 scripts/verificar_letterboxd.py --cine CCK     # sólo un cine
    python3 scripts/verificar_letterboxd.py --desde 2026-09-04 --hasta 2026-09-30

Por qué existe: cuando una función queda sin link, la tentación es escribir el
slug a mano —"romeria-2025" se adivina solo— y ahí está el problema. Un slug
inventado que existe manda a OTRA película, y eso es peor que no tener link:
nadie lo revisa después porque la fila se ve completa. Por eso el propio
data/letterboxd_overrides.json dice que todos los slugs se verifican contra
letterboxd.com antes de entrar.

Esto automatiza esa verificación. Para cada función sin link prueba los
candidatos que ya sabe armar letterboxd.py (slug directo, TMDb, DuckDuckGo),
abre la página y sólo acepta el slug si _validate_meta confirma director y año
contra lo que publica el cine. Al final imprime un bloque listo para pegar en
data/letterboxd_overrides.json, y lista aparte las que no se pudieron
confirmar: cortos de festival y estrenos del año que muchas veces todavía no
existen en Letterboxd, y que hay que dejar sin link a propósito.

Necesita red hacia letterboxd.com y TMDb. Si el entorno no la tiene, corre en
CI con el workflow verificar-letterboxd.yml (workflow_dispatch).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from letterboxd import (                                   # noqa: E402
    _validate_meta, fetch_film_page, parse_film_soup, slugify,
    search_ddg_letterboxd, tmdb_letterboxd_candidates,
)

CARTELERA = ROOT / "data" / "cartelera.json"


def candidatos(titulo: str, anio, director: str) -> list[str]:
    """URLs a probar, de la más barata a la más cara."""
    urls: list[str] = []
    base = slugify(titulo)
    if base:
        if anio:
            urls.append(f"https://letterboxd.com/film/{base}-{anio}/")
        urls.append(f"https://letterboxd.com/film/{base}/")
    try:
        # hint_original vacío: el CCK no publica el título original, y TMDb
        # igual matchea AKAs y títulos traducidos mejor que adivinar el slug.
        urls += tmdb_letterboxd_candidates(titulo, "", anio) or []
    except Exception as e:
        print(f"      (TMDb no contestó: {e})")
    try:
        consulta = f"{titulo} {director} {anio or ''} letterboxd".strip()
        urls += search_ddg_letterboxd(consulta) or []
    except Exception as e:
        print(f"      (DuckDuckGo no contestó: {e})")
    # Únicas, en orden.
    vistas, out = set(), []
    for u in urls:
        if u and u not in vistas:
            vistas.add(u)
            out.append(u)
    return out


def verificar(titulo: str, anio, director: str, duracion=None):
    """(url, meta) del primer candidato que la validación acepta, o (None, motivo)."""
    probados = 0
    for url in candidatos(titulo, anio, director):
        soup = fetch_film_page(url)
        if soup is None:
            continue
        probados += 1
        meta = parse_film_soup(soup, url)
        if not meta:
            continue
        if _validate_meta(meta, anio, director, duracion):
            return url, meta
        print(f"      ✗ {url} → {meta.get('director')!r} ({meta.get('year')}) "
              f"no coincide con {director!r} ({anio})")
    return None, ("ninguna página abrió" if not probados
                  else "abrieron páginas pero ninguna coincide")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cine", help="sólo este cine")
    ap.add_argument("--desde", help="fecha mínima (YYYY-MM-DD)")
    ap.add_argument("--hasta", help="fecha máxima (YYYY-MM-DD)")
    args = ap.parse_args()

    data = json.loads(CARTELERA.read_text(encoding="utf-8"))
    faltan: dict[str, dict] = {}
    for s in data.get("screenings", []):
        if s.get("letterboxd"):
            continue
        if args.cine and s.get("cine") != args.cine:
            continue
        if args.desde and s.get("fecha", "") < args.desde:
            continue
        if args.hasta and s.get("fecha", "") > args.hasta:
            continue
        titulo = (s.get("title_es") or "").strip()
        if not titulo:
            continue
        # Una película por clave: se repite en varias funciones.
        faltan.setdefault(titulo.lower(), {
            "title": titulo, "year": s.get("year"),
            "director": (s.get("director") or "").strip(),
            "duration": s.get("duration"), "cines": set(),
        })["cines"].add(s.get("cine", "?"))

    if not faltan:
        print("No hay funciones sin link de Letterboxd con ese filtro.")
        return 0

    print(f"Verificando {len(faltan)} película(s) sin link…\n")
    confirmados: dict[str, str] = {}
    sin_confirmar: list[tuple[str, str]] = []

    for clave, f in sorted(faltan.items()):
        cines = ", ".join(sorted(f["cines"]))
        print(f"· {f['title']} ({f['year'] or 's/año'}) — {f['director'] or 's/director'} "
              f"[{cines}]")
        url, meta = verificar(f["title"], f["year"], f["director"], f["duration"])
        if url:
            print(f"      ✅ {url}  → {meta.get('director')} ({meta.get('year')})")
            confirmados[clave] = url
        else:
            print(f"      ⚠️  sin confirmar: {meta}")
            sin_confirmar.append((f["title"], meta))

    print("\n" + "=" * 72)
    print(f"CONFIRMADOS: {len(confirmados)} · SIN CONFIRMAR: {len(sin_confirmar)}")
    if confirmados:
        print("\nPegar en data/letterboxd_overrides.json:\n")
        for clave, url in sorted(confirmados.items()):
            print(f'  {json.dumps(clave, ensure_ascii=False)}: {json.dumps(url)},')
    if sin_confirmar:
        print("\nSin confirmar — dejar SIN link, no inventar el slug:")
        for titulo, motivo in sin_confirmar:
            print(f"  · {titulo} ({motivo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
