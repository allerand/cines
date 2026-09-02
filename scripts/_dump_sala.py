#!/usr/bin/env python3
"""TEMPORAL — vuelve a correr el scraper de Sala Lúcida contra el sitio y abre
los candidatos de Letterboxd que la verificación automática no pudo confirmar.
Se borra junto con el parche a probe-acceso.yml."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scraper import scrape_sala_lucida                       # noqa: E402
from letterboxd import fetch_film_page, parse_film_soup      # noqa: E402

# Las dos que quedaron sin confirmar y que sí podrían existir en Letterboxd
# (el resto son cortos de festival). Se abren a mano y se mira qué dice la
# página: el slug no se escribe si la ficha no coincide.
CANDIDATOS = {
    "El diablo nunca duerme (Lourdes Portillo)": [
        "https://letterboxd.com/film/the-devil-never-sleeps/",
        "https://letterboxd.com/film/el-diablo-nunca-duerme/",
        "https://letterboxd.com/film/the-devil-never-sleeps-1994/",
    ],
    "Matria (Jimena Chavez)": [
        "https://letterboxd.com/film/matria-2025/",
        "https://letterboxd.com/film/matria-2026/",
        "https://letterboxd.com/film/matria-2024/",
        "https://letterboxd.com/film/matria-2022/",
    ],
}


def main() -> int:
    print("Funciones (chequeo del ciclo)\n" + "=" * 70)
    for s in sorted(scrape_sala_lucida(9), key=lambda x: (x.fecha, x.hora)):
        print(f"{s.fecha} {s.hora}  {s.title!r} ciclo={s.ciclo!r} "
              f"dir={s.director!r} año={s.year} dur={s.duration}")

    print("\n\nCandidatos de Letterboxd sin confirmar\n" + "=" * 70)
    for peli, urls in CANDIDATOS.items():
        print(f"\n• {peli}")
        for u in urls:
            soup = fetch_film_page(u)
            if soup is None:
                print(f"    {u} → no abre (404)")
                continue
            meta = parse_film_soup(soup, u) or {}
            print(f"    {u} → {meta.get('title_en')!r} / "
                  f"dir={meta.get('director')!r} año={meta.get('year')} "
                  f"dur={meta.get('duration')} país={meta.get('country')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
