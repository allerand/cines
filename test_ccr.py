#!/usr/bin/env python3
"""
Test del parseo de las páginas de evento del Centro Cultural Recoleta, sin red.

    python3 test_ccr.py

Los fixtures son el texto de dos páginas reales (8/10/2026), renglón por
renglón como lo deja get_text("\\n"):

  · ccr_encuentro_europeo — la grilla en prosa del Encuentro de Cine Europeo:
    "Sáb. 03.10 | 16 h: “Long Good Thursday”, de Mika Kaurismäki (Finlandia)"
    y la sinopsis abajo. Tomando el renglón de arriba de cada fecha como
    título, la historia del 4/10 publicó "matthias dirige una exitosa agencia
    de alquiler de amigos…" (la sinopsis de la función ANTERIOR); y el primer
    arreglo, que buscaba el título debajo de la fecha, no encontraba ninguno
    y tiraba las 16 funciones. Trae además "Dom 11.10" sin punto, dos fechas
    en una línea, un "de" sin coma, dos directores con un solo apellido y
    cuatro países.
  · ccr_sabados_superaccion — un ciclo con "Actividades": título y fecha
    abajo, con todas las funciones del año. Las de enero ("Sáb. 10.01") no
    pueden volver como si fueran de enero de 2027.
"""
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from scraper import _ccr_lineas, _ccr_parse_lineas

FIX = Path(__file__).parent / "tests" / "fixtures"
URL = "http://centroculturalrecoleta.org/agenda/encuentro-de-cine-europeo"


def funciones(nombre, hoy):
    lines = (FIX / nombre).read_text(encoding="utf-8").splitlines()
    return [(s.fecha, s.hora, s.title, s.director, s.country)
            for s in _ccr_parse_lineas(lines, URL, hoy)]


def main():
    fallas = []

    def check(nombre, got, want):
        if got != want:
            fallas.append(f"{nombre}:\n  esperado {want}\n  obtenido {got}")

    enc = funciones("ccr_encuentro_europeo.txt", date(2026, 10, 3))
    check("encuentro: la grilla entera", [(f, h, t) for f, h, t, _, _ in enc], [
        ("2026-10-03", "16:00", "Long Good Thursday"),
        ("2026-10-03", "18:00", "Peacock"),
        ("2026-10-04", "16:00", "Cara o seca"),
        ("2026-10-04", "18:00", "La Gioia"),
        ("2026-10-10", "18:00", "Smaragda"),
        ("2026-10-11", "16:00", "Gente oculta"),
        ("2026-10-11", "18:00", "Misterioso asesinato en la montaña"),
        ("2026-10-17", "18:00", "Siete días"),
        ("2026-10-25", "18:00", "Siete días"),
        ("2026-10-18", "18:00", "Voces de libertad"),
        ("2026-11-01", "18:00", "Voces de libertad"),
        ("2026-10-24", "18:00", "No hay fantasmas en la calle Dobra"),
        ("2026-10-25", "16:00", "Jippie No More!"),
        ("2026-10-31", "16:00", "La memoria del perfume de las cosas"),
        ("2026-10-31", "18:00", "Dražen"),
        ("2026-11-01", "16:00", "Songs of Slow Burning Earth"),
    ])
    ficha = {t: (d, c) for _, _, t, d, c in enc}
    check("encuentro: director y país", [ficha.get(t) for t in (
        "Long Good Thursday", "Cara o seca", "La memoria del perfume de las cosas",
        "Dražen", "Songs of Slow Burning Earth")], [
        ("Mika Kaurismäki", "Finlandia"),
        ("Lenny Guit, Harpo Guit", "Bélgica"),
        ("António Fonseca", "Portugal"),
        ("Danilo Serbedzija, Ljubo Zdjelarevic", "Croacia"),
        ("Olha Zhurba", "Ucrania, Dinamarca, Francia, Suecia"),
    ])
    check("encuentro: ninguna sinopsis como título",
          [t for _, _, t, _, _ in enc if len(t.split()) > 8], [])

    check("superacción: sólo lo que viene",
          [(f, h, t) for f, h, t, _, _ in funciones("ccr_sabados_superaccion.txt", date(2026, 10, 8))],
          [("2026-10-10", "16:00", "Prínicipe Valiente")])
    # En diciembre la ventana de 90 días ya llega a marzo de 2027; los
    # sábados 10.01, 14.02 y 14.03 son de 2026 (en 2027 caen domingo) y no
    # tienen que aparecer.
    check("superacción: enero no vuelve en 2027",
          funciones("ccr_sabados_superaccion.txt", date(2026, 12, 20)), [])

    comedias = """
Comedias de terror
Viernes de octubre | 18 h
Cine | La hora del espanto
Vie. 09.10 | 18 h | Cine
Cine | El club del terror
Vie. 16.10 y Vie. 23.10 | 18 h | Cine
Taller | Maquillaje de monstruos
Sáb. 17.10 | 15 h | Taller
Música | Banda de sonido
Sáb. 17.10 | 20 h
Horarios
Vie. 09.10 | 18 h | Cine
"""
    check("ciclo: título → fecha, sólo cine",
          [(s.fecha, s.hora, s.title) for s in
           _ccr_parse_lineas(comedias.splitlines(), URL, date(2026, 10, 8))], [
        ("2026-10-09", "18:00", "La hora del espanto"),
        ("2026-10-16", "18:00", "El club del terror"),
        ("2026-10-23", "18:00", "El club del terror"),
    ])

    html = ("<p>Sáb. 03.10 | 16 h: <strong>“Long Good Thursday”</strong>, de "
            "<em>Mika Kaurismäki</em> (Finlandia)<br>Mientras hace las compras…</p>")
    check("html: las negritas no parten la línea de la fecha",
          _ccr_lineas(BeautifulSoup(html, "html.parser"))[0],
          "Sáb. 03.10 | 16 h: “Long Good Thursday”, de Mika Kaurismäki (Finlandia)")

    if fallas:
        print("\n".join(fallas))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
