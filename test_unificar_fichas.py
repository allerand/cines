#!/usr/bin/env python3
"""
Tests de unificar_fichas: una sola ficha por película.

    python3 test_unificar_fichas.py

Cada sala escribe la misma película a su manera y la ficha de la sala manda
sobre la de Letterboxd, así que la misma película salía distinta según dónde
se diera. En Madrid, La bola negra (271 funciones, un solo Letterboxd) tenía
dos títulos, tres formas de escribir a los directores, dos países y dos
duraciones. Las funciones que comparten Letterboxd muestran la misma ficha.
"""
import sys

from scraper import unificar_fichas

fallas = 0


def ok(nombre, obtuvo, esperado):
    global fallas
    if obtuvo == esperado:
        print(f"  ✅ {nombre}")
    else:
        fallas += 1
        print(f"  ❌ {nombre}\n     esperado {esperado!r}\n     obtuvo   {obtuvo!r}")


LB = "https://letterboxd.com/film/la-bola-negra/"


def f(cine, **k):
    base = dict(cine=cine, title_es="La bola negra", title_en="La Bola Negra", original_title="",
                director="Javier Ambrossi, Javier Calvo", country="España, Francia", year=2026,
                duration=159, genre="Drama, Bélica", letterboxd=LB)
    base.update(k)
    return base


print("La bola negra: cada sala a su manera")
filas = [f("Embajadores Glorieta"), f("Embajadores Ercilla"),
         f("Cines Ideal", director="Javier Calvo"),
         f("Cines Princesa", title_es="La Bola Negra", duration=155),
         f("Cines Princesa", title_es="La Bola Negra", duration=155),
         f("Cines Princesa", title_es="La Bola Negra", duration=155),
         f("Golem Madrid", director="Javier Calvo y Javier Ambrossi", country="España")]
n = unificar_fichas(filas)
ok("todas con el mismo título, escrito como oración", {x["title_es"] for x in filas}, {"La bola negra"})
ok("los dos directores, con coma", {x["director"] for x in filas}, {"Javier Ambrossi, Javier Calvo"})
ok("el país que dice la mayoría de las salas", {x["country"] for x in filas}, {"España, Francia"})
ok("la duración que dice la mayoría de las salas, no de las funciones", {x["duration"] for x in filas}, {159})
ok("cuenta las funciones que cambió", n, 5)

print("\nMejor escrito antes que más usado")
filas = [f("Multiplex Belgrano", title_es="Hope:el Primer Impacto", letterboxd="lb/hope"),
         f("Multiplex Lavalle", title_es="Hope:el Primer Impacto", letterboxd="lb/hope"),
         f("Multiplex Pilar", title_es="Hope:el Primer Impacto", letterboxd="lb/hope"),
         f("Cinépolis Houssay", title_es="Hope: El primer impacto", letterboxd="lb/hope")]
unificar_fichas(filas)
ok("con espacio después de los dos puntos", {x["title_es"] for x in filas}, {"Hope: El primer impacto"})
filas = [f("Multiplex Belgrano", title_es="La Vida Es Asi", letterboxd="lb/vida"),
         f("Multiplex Pilar", title_es="La Vida Es Asi", letterboxd="lb/vida"),
         f("Cine Lorca", title_es="La vida es así", letterboxd="lb/vida")]
unificar_fichas(filas)
ok("con tilde", {x["title_es"] for x in filas}, {"La vida es así"})

print("\nLo que no se toca")
filas = [f("Cineteca Madrid", title_es="Eugènia Balcells. Sesión I", duration=60, letterboxd="lb/balcells"),
         f("Cineteca Madrid", title_es="Eugènia Balcells. Sesión II", duration=74, letterboxd="lb/balcells")]
unificar_fichas(filas)
ok("dos programas numerados con el mismo Letterboxd", [x["title_es"] for x in filas],
   ["Eugènia Balcells. Sesión I", "Eugènia Balcells. Sesión II"])
ok("cada uno con su duración", [x["duration"] for x in filas], [60, 74])
filas = [f("MALBA", title_es="Una", letterboxd=""), f("MALBA", title_es="Otra", letterboxd="")]
ok("funciones sin Letterboxd", unificar_fichas(filas), 0)

print("\nLos datos vacíos se completan")
filas = [f("Cine Lorca", director="", country="", year=None, letterboxd="lb/x"), f("Cine Cosmos", letterboxd="lb/x")]
unificar_fichas(filas)
ok("director, país y año", (filas[0]["director"], filas[0]["country"], filas[0]["year"]),
   ("Javier Ambrossi, Javier Calvo", "España, Francia", 2026))

print()
if fallas:
    print(f"❌ {fallas} fallas")
    sys.exit(1)
print("✅ todo bien")
