#!/usr/bin/env python3
"""TEMPORAL — lee el título canónico de las fichas de Letterboxd ya verificadas
y muestra cómo queda el casing de cada fila después del post-proceso de run.py.
Se borra junto con el parche a probe-acceso.yml."""
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper import scrape_sala_lucida                       # noqa: E402
from letterboxd import fetch_film_page, parse_film_soup      # noqa: E402

LINKS = [
    "https://letterboxd.com/film/abalos-una-historia-de-5-hermanos/",
    "https://letterboxd.com/film/fight-club/",
    "https://letterboxd.com/film/si-muero-antes-de-despertar/",
    "https://letterboxd.com/film/suerte-josefa/",
    "https://letterboxd.com/film/tierra-citrus/",
    "https://letterboxd.com/film/una-cancion-para-mi-tierra/",
    "https://letterboxd.com/film/matria-2024/",
    "https://letterboxd.com/film/the-devil-never-sleeps/",
    # Los cortos: se confirma que NO están, para dejarlos sin link a conciencia.
    "https://letterboxd.com/film/casi-ciudadanos/",
    "https://letterboxd.com/film/la-sirena-mecanica/",
]


def helpers():
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    ini = src.index("    SPANISH_STOPWORDS = {")
    fin = src.index("    def _fix_country_caps(s: str) -> str:")
    ns = {"re": re}
    exec(textwrap.dedent(src[ini:fin]), ns)
    return ns["_title_case_es"], ns["_fix_caps"]


def main() -> int:
    title_case, fix_caps = helpers()

    print("Fichas de Letterboxd (título canónico)\n" + "=" * 70)
    for u in LINKS:
        soup = fetch_film_page(u)
        if soup is None:
            print(f"  {u.split('/film/')[1]:42} → no existe (404)")
            continue
        m = parse_film_soup(soup, u) or {}
        print(f"  {u.split('/film/')[1]:42} → title_en={m.get('title_en')!r} "
              f"original={m.get('original_title')!r} dir={m.get('director')!r} "
              f"año={m.get('year')}")

    print("\n\nCasing final de cada fila (lo que vería la web)\n" + "=" * 70)
    for s in sorted(scrape_sala_lucida(9), key=lambda x: (x.fecha, x.hora)):
        scraped = s.title
        titulo = title_case(scraped) if len(scraped) > 3 and scraped.isupper() else scraped
        print(f"{s.fecha} {s.hora}  {titulo!r}")
        print(f"              dir={fix_caps(s.director)!r} ciclo={fix_caps(s.ciclo)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
