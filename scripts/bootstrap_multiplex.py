#!/usr/bin/env python3
"""
Mete la cartelera de Multiplex en data/cartelera.json sin esperar al scrape.

Es un puente de una sola vez: el scrape nocturno (run.py) va a regenerar todo
igual, pero mientras tanto los chips de Multiplex quedan vacíos en la web.
El merge de run.py preserva las funciones comerciales futuras, así que lo que
escribe esto sobrevive hasta que la corrida real lo reemplace con datos
enriquecidos.

Usa el mismo scrape_multiplex() del scraper — no duplica el parser.

Metadata: no hay red para TMDb/Letterboxd acá, así que se copia de las
funciones que YA están en cartelera.json. Los comerciales pasan las mismas
películas, con lo cual casi todo matchea; lo que no, entra con los campos
vacíos y lo completa el enrichment en la próxima corrida.

Uso:
    python3 scripts/bootstrap_multiplex.py            # muestra qué haría
    python3 scripts/bootstrap_multiplex.py --escribir # lo escribe
"""

import json
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CARTELERA = RAIZ / "data" / "cartelera.json"

# Orden de campos de cada función, igual que lo escribe run.py.
CAMPOS = ["cine", "fecha", "hora", "title_es", "title_en", "original_title",
          "director", "country", "year", "duration", "genre", "letterboxd",
          "ticket_url", "ciclo"]
# Los que se copian de una función ya enriquecida con el mismo título.
CAMPOS_META = ["title_en", "original_title", "director", "country", "year",
               "duration", "genre", "letterboxd"]


def clave_titulo(t: str) -> str:
    """Título normalizado para matchear metadata: sin acentos, ni caso, ni signos."""
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return "".join(c for c in t if c.isalnum() or c.isspace()).strip()


def orden(x):
    """Mismo criterio que run.py: por fecha y hora."""
    try:
        d = datetime.strptime(x["fecha"], "%Y-%m-%d").date()
    except ValueError:
        d = date.max
    try:
        h = datetime.strptime(x["hora"], "%H:%M").time()
    except ValueError:
        h = time(23, 59)
    return (d, h)


def main(escribir: bool) -> int:
    from scraper import scrape_multiplex

    print("Bajando multiplex.com.ar…")
    funciones = scrape_multiplex()
    if not funciones:
        print("✗ 0 funciones. Nada que escribir.")
        return 1

    print(f"\n{len(funciones)} funciones")
    for cine, n in Counter(f.cine for f in funciones).most_common():
        fechas = sorted({f.fecha for f in funciones if f.cine == cine})
        print(f"  {cine:<22} {n:>4} funciones · {len(fechas)} días "
              f"({fechas[0]} → {fechas[-1]})")

    titulos = sorted({f.title for f in funciones})
    print(f"\n{len(titulos)} títulos:")
    for t in titulos:
        print(f"  · {t}")

    data = json.loads(CARTELERA.read_text(encoding="utf-8"))
    previas = data.get("screenings", [])

    # Índice título → metadata, armado con lo que ya está enriquecido. Gana la
    # entrada con más campos llenos (una función vieja puede haber quedado a
    # medio enriquecer).
    meta_por_titulo = {}
    for s in previas:
        for campo in ("title_es", "original_title", "title_en"):
            k = clave_titulo(s.get(campo, ""))
            if not k:
                continue
            cand = {c: s.get(c) for c in CAMPOS_META}
            llenos = sum(1 for v in cand.values() if v not in (None, "", 0))
            if llenos > meta_por_titulo.get(k, (None, -1))[1]:
                meta_por_titulo[k] = (cand, llenos)

    existentes = {(s.get("cine"), s.get("title_es"), s.get("fecha"), s.get("hora"))
                  for s in previas}

    nuevas, con_meta, sin_meta = [], 0, set()
    for f in funciones:
        if (f.cine, f.title, f.fecha, f.hora) in existentes:
            continue
        fila = {c: "" for c in CAMPOS}
        fila.update(cine=f.cine, fecha=f.fecha, hora=f.hora,
                    title_es=f.title, ticket_url=f.ticket_url)
        fila["year"] = None
        fila["duration"] = None
        hit = meta_por_titulo.get(clave_titulo(f.title))
        if hit:
            fila.update({c: v for c, v in hit[0].items() if v not in (None, "")})
            con_meta += 1
        else:
            sin_meta.add(f.title)
        nuevas.append(fila)

    print(f"\n{len(nuevas)} funciones nuevas — {con_meta} con metadata copiada "
          f"de la cartelera actual")
    if sin_meta:
        print(f"  sin metadata (las completa el próximo scrape): "
              f"{sorted(sin_meta)}")

    if not escribir:
        print("\n(simulacro) Volvé a correrlo con --escribir para aplicarlo.")
        return 0

    salida = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "screenings": sorted(previas + nuevas, key=orden),
    }
    # Mismo formato exacto que run.py, incluida la ausencia de salto final:
    # cualquier diferencia ensucia el diff de la próxima corrida.
    CARTELERA.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {len(salida['screenings'])} funciones en {CARTELERA}")
    print("\nAhora:\n"
          "    git add data/cartelera.json\n"
          '    git commit -m "data: cartelera de Multiplex hasta el próximo scrape"\n'
          "    git push origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main("--escribir" in sys.argv))
