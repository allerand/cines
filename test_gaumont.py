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
