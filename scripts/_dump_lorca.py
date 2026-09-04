#!/usr/bin/env python3
"""TEMPORAL — ¿de dónde salen los horarios del Lorca?

La cartelera publica "La invitación" 15:40 y 22:50 desde el 29/8, cuando la
grilla del cine (válida 03/09–09/09) la da a las 20:05. Esto imprime el bloque
"FUNCIONES DE" tal como lo ve el parser y lo que el parser saca de él.
Se borra junto con el parche a probe-acceso.yml.
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper import (LANACION_BASE, fetch_html,                  # noqa: E402
                     _parse_lanacion_film_funciones,
                     _scrape_lanacion_sala)

SLUG, SALA = "lorca-sa110", "Lorca"


def main() -> int:
    print(f"hoy para el runner: {date.today().isoformat()}\n")
    sala_soup = fetch_html(f"{LANACION_BASE}/cartelera-de-cine/sala/{SLUG}")
    paths, vistos = [], set()
    for a in sala_soup.find_all("a", href=re.compile(r"^/cartelera-de-cine/pelicula/")):
        if a["href"] not in vistos:
            vistos.add(a["href"])
            paths.append(a["href"])
    print(f"La Nación lista {len(paths)} películas en el Lorca\n" + "=" * 70)

    for path in paths:
        det = fetch_html(LANACION_BASE + path)
        text = det.get_text("\n", strip=True)
        h1 = det.find("h1")
        titulo = h1.get_text(strip=True) if h1 else path
        ini, fin = text.find("FUNCIONES DE"), text.find("OTRAS PELÍCULAS")
        bloque = text[ini: fin if fin > ini else len(text)] if ini >= 0 else ""
        parseado = _parse_lanacion_film_funciones(text)
        print(f"\n── {titulo}")
        print(f"   parser → Lorca={parseado.get(SALA)!r}  "
              f"(salas vistas: {list(parseado)[:6]})")
        if "invitaci" in titulo.lower() or not parseado.get(SALA):
            print("   ---- bloque FUNCIONES DE, crudo ----")
            for ln in bloque.split("\n")[:45]:
                print(f"   | {ln}")

    print("\n\nLo que devuelve el scraper hoy\n" + "=" * 70)
    for s in sorted(_scrape_lanacion_sala(SLUG, SALA, "Cine Lorca", "x"),
                    key=lambda x: x.hora):
        print(f"  {s.fecha} {s.hora}  {s.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
