"""Corre el scraper de Arthaus contra la web real y muestra lo que trae.

    python3 scripts/test_arthaus.py

Sirve para mirar la programación cruda antes de que la toque el enrichment.
El scrape de Arthaus dejó de necesitar playwright cuando pasó de /agenda/ a
/cine/: el HTML servido ya trae todas las películas del mes.
"""
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.append(str(Path(__file__).resolve().parent.parent))

from scraper import scrape_arthaus


def main():
    screenings = scrape_arthaus(semanas=3)

    print(f"\nTotal Arthaus: {len(screenings)} funciones\n")
    for s in sorted(screenings, key=lambda x: (x.fecha, x.hora)):
        print(json.dumps(asdict(s), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
