#!/usr/bin/env python3
"""
Test del merge de run.py: qué funciones de la corrida anterior sobreviven.

    python3 test_merge_horarios.py

El caso que lo motiva es el Cine Lorca del 3/9/2026. La sala estrenó su semana
nueva (03/09-09/09) con "La invitación" a las 20:05, pero La Nación —de donde
sale el Lorca desde que IMDb dejó de responder— todavía publicaba la grilla
anterior cuando corrió el scrape de las 22:10 de Buenos Aires. Se guardaron los
15:40 y 22:50 de la semana pasada.

Lo grave no fue equivocarse una vez: fue que no había forma de corregirlo. La
preservación de las funciones de HOY reponía cualquier fila de la corrida
anterior que faltara en la nueva, sin mirar si el scrape fresco ya traía esa
misma película. Los 20:05 correctos entraban AL LADO de los viejos, y las tres
filas convivían hasta que la fecha pasaba.

La regla que se prueba acá: si el scrape de hoy trae (cine, película, fecha),
sus horarios son los horarios. Lo que la corrida anterior diga de esa misma
película ese mismo día es una versión vieja y se descarta. Una película que el
scrape de hoy NO trae sigue preservándose — de eso depende el Lugones, que
pierde eventos del listado del CTBA en su último día.
"""
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent


def merge_de_run(screenings_out, previas, today_str):
    """Corre el bloque de merge de run.py sobre dos listas de funciones.

    Se extrae del fuente en vez de importar run.py porque importarlo arranca
    playwright y pide red. Lo que se prueba es el código que corre en
    producción, no una reimplementación.
    """
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    ini = src.index("            def _key(s):")
    fin = src.index("        except Exception as e:\n            print(f\"  ↳ Merge omitido:")
    cuerpo = textwrap.dedent(src[ini:fin])
    # El bloque real usa estos nombres del scope de run_scraper.
    ns = {
        "screenings_out": screenings_out,
        "prev_data": {"screenings": previas},
        "today_str": today_str,
        "COMMERCIAL_PREFIXES": ("Cinemark", "Hoyts", "Cinépolis", "Showcase", "Multiplex"),
        "CINES_CON_CACHE": {"Centro Cultural Borges": 3, "CCK": 1, "Bellas Artes": 1},
        "urlparse": __import__("urllib.parse", fromlist=["urlparse"]).urlparse,
        "sort_key": lambda x: (x.get("fecha", ""), x.get("hora", "")),
        "print": lambda *a, **k: None,
        "re": re,
    }
    exec(cuerpo, ns)
    return ns["screenings_out"]


def f(cine, title, fecha, hora, url="https://cinelorca.wixsite.com/cine-lorca"):
    return {"cine": cine, "title_es": title, "fecha": fecha, "hora": hora,
            "ticket_url": url}


HOY = "2026-09-04"
fallos = 0


def chequear(que, ok, detalle=None):
    global fallos
    print(f"  {'✅' if ok else '❌'} {que}")
    if not ok:
        fallos += 1
        if detalle is not None:
            print(f"     → {detalle}")


def main() -> int:
    print("El Lorca corrige un horario")
    # Hoy el scrape trae la grilla nueva; la corrida anterior tenía la vieja.
    frescas = [f("Cine Lorca", "La invitación", HOY, "20:05"),
               f("Cine Lorca", "Pepita La Pistolera", HOY, "16:20"),
               f("Cine Lorca", "Pepita La Pistolera", HOY, "22:30")]
    previas = [f("Cine Lorca", "La invitación", HOY, "15:40"),
               f("Cine Lorca", "La invitación", HOY, "22:50"),
               f("Cine Lorca", "Pepita La Pistolera", HOY, "16:20")]
    out = merge_de_run(list(frescas), previas, HOY)
    horas = sorted(s["hora"] for s in out if s["title_es"] == "La invitación")
    chequear("los horarios viejos de la misma película no vuelven",
             horas == ["20:05"], horas)
    chequear("las otras funciones del día siguen intactas",
             sorted(s["hora"] for s in out if s["title_es"] == "Pepita La Pistolera")
             == ["16:20", "22:30"])

    print("\nEl Lugones pierde un evento del listado")
    # El ciclo Portabella se cae del listado del CTBA; el resto del Lugones
    # scrapea bien. Sus funciones de hoy tienen que sobrevivir: son las únicas
    # que quedan de ese evento.
    frescas = [f("Sala Lugones", "Cerdos y acorazados", HOY, "15:00", "https://entradasba.buenosaires.gob.ar/evento/aaa")]
    previas = [f("Sala Lugones", "Cerdos y acorazados", HOY, "15:00", "https://entradasba.buenosaires.gob.ar/evento/aaa"),
               f("Sala Lugones", "Tren de sombras", HOY, "18:00", "https://entradasba.buenosaires.gob.ar/evento/bbb")]
    out = merge_de_run(list(frescas), previas, HOY)
    titulos = sorted(s["title_es"] for s in out)
    chequear("la película que el scrape de hoy no trajo se preserva",
             titulos == ["Cerdos y acorazados", "Tren de sombras"], titulos)

    print("\nLo que ya se protegía sigue protegido")
    manana = "2026-09-05"
    frescas = [f("Cinemark Palermo", "La invitación", HOY, "18:20", "https://www.cinemark.com.ar/")]
    previas = [f("Cinemark Palermo", "La invitación", manana, "18:20", "https://www.cinemark.com.ar/")]
    out = merge_de_run(list(frescas), previas, HOY)
    chequear("una función futura de un comercial se preserva",
             any(s["fecha"] == manana for s in out), out)
    # Mismo título y mismo cine pero OTRO día: no es el mismo horario corregido.
    frescas = [f("Cine Lorca", "La invitación", HOY, "20:05")]
    previas = [f("Cine Lorca", "La invitación", HOY, "20:05")]
    out = merge_de_run(list(frescas), previas, HOY)
    chequear("una función idéntica no se duplica", len(out) == 1, out)

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
