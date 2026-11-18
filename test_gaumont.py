#!/usr/bin/env python3
"""
Tests del Gaumont (API de Cinexo desde octubre de 2026).

    python3 test_gaumont.py

La API no trae el país: sale de la ficha de cada película, que lo escribe
separado por espacios y como venga ("ESPAÑA FRANCIA", "argentina").
"""
import sys

from scraper import _gaumont_paises

fallas = 0


def ok(nombre, obtuvo, esperado):
    global fallas
    if obtuvo == esperado:
        print(f"  ✅ {nombre}")
    else:
        fallas += 1
        print(f"  ❌ {nombre}\n     esperado {esperado!r}\n     obtuvo   {obtuvo!r}")


print("Países de la ficha")
ok("dos países separados por espacio", _gaumont_paises("ESPAÑA FRANCIA"), "ESPAÑA, FRANCIA")
ok("país de dos palabras entero", _gaumont_paises("ESTADOS UNIDOS"), "ESTADOS UNIDOS")
ok("compuesto y simple", _gaumont_paises("REINO UNIDO FRANCIA"), "REINO UNIDO, FRANCIA")
ok("con comas queda igual", _gaumont_paises("Chile, Argentina"), "Chile, Argentina")
ok("minúscula", _gaumont_paises("argentina"), "Argentina")
ok("vacío", _gaumont_paises(""), "")

print()
if fallas:
    print(f"❌ {fallas} fallas")
    sys.exit(1)
print("✅ todo bien")

# --- Ciclo pegado adelante del título y comas sin espacio --------------------
# El 18/11/2026 Jeanne Dielman figuraba en la API como "CICLO CALIGARI
# NOVIEMBRE 2026 - JEANNE DIELMAN,23,QUAI DU COMMERCE,1080 BRUXELLES" y salía
# todo eso como título, sin ciclo y sin ficha.
from scraper import _gaumont_titulo_y_ciclo
assert _gaumont_titulo_y_ciclo(
    "CICLO CALIGARI NOVIEMBRE 2026 - JEANNE DIELMAN,23,QUAI DU COMMERCE,1080 BRUXELLES") == (
    "JEANNE DIELMAN, 23, QUAI DU COMMERCE, 1080 BRUXELLES", "Ciclo Caligari")
assert _gaumont_titulo_y_ciclo("Festival Caligari Noviembre 2026 - LA CONVERSACION") == (
    "LA CONVERSACION", "Festival Caligari")
assert _gaumont_titulo_y_ciclo("RETRATO,ELOGIO AL DUELO") == ("RETRATO, ELOGIO AL DUELO", "")
assert _gaumont_titulo_y_ciclo("10,5 GRADOS") == ("10,5 GRADOS", "")
assert _gaumont_titulo_y_ciclo("SPIDER-MAN - EL REGRESO") == ("SPIDER-MAN - EL REGRESO", "")
assert _gaumont_titulo_y_ciclo("RECEN POR MI: LA HISTORIA DE FRANCISCO") == (
    "RECEN POR MI: LA HISTORIA DE FRANCISCO", "")
print("✓ gaumont: el ciclo de adelante va a su columna (sin el mes) y las comas llevan espacio")
