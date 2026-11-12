#!/usr/bin/env python3
"""Ninguna bandera en la web (pedido de Mateo, 12/11/2026).

El post del Cosmos de la semana del 12/11 les pegó la bandera del país a los
títulos ("🎬 🇷🇴 KONTINENTAL '25") y salieron así a la web y a las stories.
scraper.sin_banderas las saca de cualquier texto, y run.py la aplica a todas
las funciones antes del enrichment y otra vez sobre la lista final. Acá se
prueba esa limpieza y que ningún JSON publicado tenga una bandera.

    python3 test_banderas.py
"""
import json
from pathlib import Path

from scraper import Screening, limpiar_banderas, sin_banderas

ESCOCIA = "🏴\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F"

CASOS = {
    "🇷🇴 KONTINENTAL '25": "KONTINENTAL '25",
    "🇦🇷LA CASA": "LA CASA",
    "Tiempos de ilusión 🇫🇷": "Tiempos de ilusión",
    "🇫🇷🇧🇪 LOS DOMINGOS": "LOS DOMINGOS",
    "🇦🇷 | LA CASA": "LA CASA",
    "LA CASA (🇦🇷)": "LA CASA",
    f"TRAINSPOTTING {ESCOCIA}": "TRAINSPOTTING",
    "🏳️‍🌈 Ciclo de cine queer": "Ciclo de cine queer",
    "🏴‍☠️ Piratas": "Piratas",
    # Sin banderas, el texto queda igual. Otros emojis no son banderas.
    "Kontinental '25": "Kontinental '25",
    "¡Al Hollywood parisino!": "¡Al Hollywood parisino!",
    "🎬 Cine": "🎬 Cine",
    "": "",
}

# Lo que lee la web: las dos carteleras y los festivales cargados a mano.
DATA = Path(__file__).parent / "data"
PUBLICADOS = [DATA / "cartelera.json", DATA / "cartelera-madrid.json",
              DATA / "festivales.json", *sorted(DATA.glob("festival-*.json"))]


def textos(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from textos(v)
    elif isinstance(o, list):
        for v in o:
            yield from textos(v)


def main() -> int:
    fallos = 0

    def chequear(que: str, ok: bool) -> None:
        nonlocal fallos
        fallos += not ok
        print(f"  {'✅' if ok else '❌'} {que}")

    for entrada, esperado in CASOS.items():
        sale = sin_banderas(entrada)
        chequear(f"{entrada!r} → {sale!r}", sale == esperado)

    # Un Screening recién scrapeado y una fila de cartelera.json.
    s = Screening(cine="Cine Cosmos", title="🇷🇴 KONTINENTAL '25", fecha="2026-11-12",
                  hora="16:35", country="🇷🇴 Rumania", ciclo="🇫🇷 Semana del cine francés")
    chequear("Screening: título, país y ciclo",
             limpiar_banderas(s) and (s.title, s.country, s.ciclo)
             == ("KONTINENTAL '25", "Rumania", "Semana del cine francés"))
    fila = {"title_es": "🇦🇷 La Casa", "title_en": "🇦🇷 LA CASA", "year": 2025,
            "ticket_url": "https://www.instagram.com/p/DfngQV0nWTs/"}
    chequear("fila de cartelera.json: title_es y title_en",
             limpiar_banderas(fila) and fila == {
                 "title_es": "La Casa", "title_en": "LA CASA", "year": 2025,
                 "ticket_url": "https://www.instagram.com/p/DfngQV0nWTs/"})
    chequear("una fila sin banderas no cambia", not limpiar_banderas({"title_es": "La Casa"}))

    for p in PUBLICADOS:
        if not p.exists():
            continue
        malos = sorted({t for t in textos(json.loads(p.read_text(encoding="utf-8")))
                        if sin_banderas(t) != t})
        chequear(f"{p.relative_to(DATA.parent)}: banderas {malos[:5] or 'ninguna'}", not malos)

    print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
