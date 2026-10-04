#!/usr/bin/env python3
"""
Test del parseo de las páginas de evento del Centro Cultural Recoleta, sin red.

    python3 test_ccr.py

El CCR escribe sus funciones de dos maneras:

  · título → fecha: los ciclos chicos ("Comedias de terror"), que el parser
    siempre leyó bien.
  · fecha → título → sinopsis: el Encuentro de Cine Europeo 2026. Leyendo el
    renglón anterior a la fecha como título, la historia del 4/10 publicó
    "matthias dirige una exitosa agencia de alquiler de amigos…" (la sinopsis
    de la función ANTERIOR) y el 3/10 a las 16 h salió como película el
    encabezado "Programación en el Ccr".

Los textos reproducen el orden de renglones que dejó ver el scrape del 3/10;
los títulos de las películas son de relleno.
"""
import sys
from datetime import date

from scraper import _ccr_parse_lineas

HOY = date(2026, 10, 3)
URL = "http://centroculturalrecoleta.org/agenda/encuentro-de-cine-europeo"

ENCUENTRO = """
Encuentro de Cine Europeo
Programación en el Ccr
Sáb. 03.10 | 16 h | Cine
Hojas de otoño
Finlandia, 2023, 81 min
Mientras hace las compras un anciano conoce a Saimi, una mujer cuya presencia despierta en él recuerdos olvidados.
Sáb. 03.10 | 18 h | Cine
Cine | Amigos de alquiler
Dirección: Fulano de Tal
Matthias dirige una exitosa agencia de alquiler de amigos pero en cuanto su novia Sophia rompe con él, su vida se convierte en un absurdo caos.
Dom. 04.10 | 16 h | Cine
Una sinopsis sin título arriba, que no tiene que terminar publicada como si fuera el nombre de la película.
Dom. 04.10 | 18 h | Cine
La reina de las apuestas
Armande Pigeon es la reina de las travesuras. En Bruselas le cuesta llegar a fin de mes.
"""

COMEDIAS = """
Comedias de terror
Cine | La hora del espanto
Vie. 09.10 | 18 h | Cine
Cine | El club del terror
Vie. 16.10 y Vie. 23.10 | 18 h | Cine
Taller | Maquillaje de monstruos
Sáb. 17.10 | 15 h | Taller
"""


def funciones(texto):
    return [(s.fecha, s.hora, s.title) for s in _ccr_parse_lineas(texto.splitlines(), URL, HOY)]


def main():
    fallas = []

    def check(nombre, got, want):
        if got != want:
            fallas.append(f"{nombre}:\n  esperado {want}\n  obtenido {got}")

    check("encuentro (fecha → título → sinopsis)", funciones(ENCUENTRO), [
        ("2026-10-03", "16:00", "Hojas de otoño"),
        ("2026-10-03", "18:00", "Amigos de alquiler"),
        # 04.10 16 h: sin título → se descarta, no se publica la sinopsis.
        ("2026-10-04", "18:00", "La reina de las apuestas"),
    ])
    check("comedias (título → fecha)", funciones(COMEDIAS), [
        ("2026-10-09", "18:00", "La hora del espanto"),
        ("2026-10-16", "18:00", "El club del terror"),
        ("2026-10-23", "18:00", "El club del terror"),
    ])

    if fallas:
        print("\n".join(fallas))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
