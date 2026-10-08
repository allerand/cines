#!/usr/bin/env python3
"""
Tests de unificar_ciclos_festivales: un solo nombre de ciclo por festival.

    python3 test_festivales_ciclos.py

En la web, un festival de Buenos Aires es una búsqueda en la cartelera por el
nombre literal de su ciclo. Eso trae todas sus funciones sólo si todas las
salas lo escriben igual, y cada una lo escribe a su manera: el MALBA pone
"Asterisco Festival Internacional de Cine LGBTIQ+", otra sala pondría
"Asterisco" a secas o "ASTERISCO - Competencia". El scraper las lleva todas al
`ciclo` de data/festivales.json, conservando la sección.
"""
import json
import sys
from pathlib import Path

from scraper import Screening, titulo_norm, unificar_ciclos_festivales

ROOT = Path(__file__).parent
fallas = 0


def ok(nombre, obtuvo, esperado):
    global fallas
    if obtuvo == esperado:
        print(f"  ✅ {nombre}")
    else:
        fallas += 1
        print(f"  ❌ {nombre}\n     esperado {esperado!r}\n     obtuvo   {obtuvo!r}")


ASTERISCO = "Asterisco Festival Internacional de Cine LGBTIQ+"
REGISTRO = [
    {"slug": "asterisco", "nombre": "Asterisco", "ciclo": ASTERISCO, "alias": ["Asterisco"]},
    {"slug": "inusual", "nombre": "Festival de Cine Inusual",
     "ciclo": "21.° Festival de Cine Inusual de Buenos Aires", "alias": ["Festival de Cine Inusual"]},
    # Los de afuera tienen su propio archivo: no se tocan ciclos por ellos.
    {"slug": "fuera-de-campo", "nombre": "Fuera de Campo", "archivo": "data/x.json",
     "ciclo": "Fuera de Campo", "alias": ["Fuera de Campo"]},
]


def unificar(ciclo):
    s = {"cine": "MALBA", "ciclo": ciclo}
    unificar_ciclos_festivales([s], REGISTRO)
    return s["ciclo"]


print("Cada sala a su manera → el ciclo del registro")
ok("el nombre largo ya está bien", unificar(ASTERISCO), ASTERISCO)
ok("a secas", unificar("Asterisco"), ASTERISCO)
ok("a los gritos", unificar("ASTERISCO FESTIVAL INTERNACIONAL DE CINE LGBTIQ+"), ASTERISCO)
ok("con edición y año", unificar("3er Festival Asterisco 2026"), ASTERISCO)
ok("la sección se conserva", unificar("Asterisco - Competencia"), f"{ASTERISCO} - Competencia")
ok("la sección del nombre largo también", unificar(f"{ASTERISCO} – Foco Brasil"), f"{ASTERISCO} - Foco Brasil")
ok("sin tildes ni caja", unificar("festival de cine INUSUAL"), "21.° Festival de Cine Inusual de Buenos Aires")

print("\nLo que no es del festival queda como estaba")
ok("otro ciclo", unificar("Ciclo El Romerazo"), "Ciclo El Romerazo")
ok("palabra que lo contiene", unificar("Asteriscos y comas"), "Asteriscos y comas")
ok("festival de afuera", unificar("Fuera de Campo"), "Fuera de Campo")
ok("sin ciclo", unificar(""), "")

print("\nObjetos Screening y conteo")
lista = [Screening(cine="MALBA", title="X", fecha="2026-10-22", hora="18:00", ciclo="Asterisco"),
         Screening(cine="MALBA", title="Y", fecha="2026-10-22", hora="20:00", ciclo=ASTERISCO),
         Screening(cine="CCK", title="Z", fecha="2026-10-22", hora="20:00", ciclo="Cine irlandés")]
_, n = unificar_ciclos_festivales(lista, REGISTRO)
ok("Screening", lista[0].ciclo, ASTERISCO)
ok("cuenta sólo las que cambió", n, 1)

print("\nEl registro de verdad")
registro = json.loads((ROOT / "data" / "festivales.json").read_text(encoding="utf-8"))["festivales"]
for f in registro:
    if f.get("archivo"):
        continue
    ok(f"{f['slug']}: tiene ciclo", bool(f.get("ciclo")), True)
    # El ciclo tiene que pasar por la unificación sin cambiar: si no, la web
    # buscaría un texto que no queda en ninguna función.
    s = {"ciclo": f["ciclo"]}
    unificar_ciclos_festivales([s], registro)
    ok(f"{f['slug']}: el ciclo es estable", s["ciclo"], f["ciclo"])
    for a in f.get("alias", []):
        ok(f"{f['slug']}: alias '{a}' tiene palabras", bool(titulo_norm(a)), True)

print()
if fallas:
    print(f"❌ {fallas} fallas")
    sys.exit(1)
print("✅ todo bien")
