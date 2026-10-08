#!/usr/bin/env python3
"""
Test local del parser del programa del Lugones (parse_ctba_program_text), sin
red ni navegador.

    python3 test_lugones_program.py

Lo que se chequea es el modo de falla que rompió el cierre del DocBuenosAires:
si una cabecera "A las X horas" no matchea, las películas de esa función NO
desaparecen — se le suman al bloque anterior y salen publicadas con el horario
de OTRA función. Es el error más caro del scraper del Lugones (alguien llega
tres horas antes), así que el parser tiene que aceptar todas las variantes con
las que el CTBA escribe el horario.
"""
from scraper import _ctba_partir_por_mes, parse_ctba_program_text

# Formato real de la página /ver/ del CTBA: encabezado de día, cabecera de
# horario, y cada película como TÍTULO + (original; país; año) + Dirección.
BASE = """
Domingo 23

{h1}

Pequeños poemas en prosa
(Little Poems in Prose; Rumania; 2025)
Dirección: Radu Jude, Andrei Rus
(35'; DM).

{h2}

La felicidad
(Paraguay; 2025)
Dirección: Paz Encina
(18'; DM).
"""


def parsear(h1: str, h2: str) -> dict:
    mapping = parse_ctba_program_text(BASE.format(h1=h1, h2=h2))
    return {hora: [e["title"] for e in entries] for (_dia, hora), entries in mapping.items()}


def main() -> int:
    fallos = 0

    # Variantes de escritura del horario que la página mezcla.
    variantes = [
        ("A las 14.30 horas", "A las 20.30 horas", "14:30", "20:30"),
        ("A las 14:30 horas", "A las 20:30 hs.",   "14:30", "20:30"),
        ("A las 14.30 hs",    "A las 20.30 hs",    "14:30", "20:30"),
        ("A las 14 horas",    "A las 20.30 h",     "14:00", "20:30"),
    ]
    for h1, h2, esperado1, esperado2 in variantes:
        got = parsear(h1, h2)
        ok = got.get(esperado1) == ["Pequeños poemas en prosa"] and \
             got.get(esperado2) == ["La felicidad"]
        print(f"{'ok ' if ok else 'MAL'} {h1!r} + {h2!r} → {got}")
        if not ok:
            fallos += 1

    # El modo de falla en sí: con una cabecera que el parser no reconoce, la
    # segunda película se cuelga del horario de la primera. Es lo que hay que
    # poder ver de un vistazo cuando un cine cambia cómo escribe la grilla.
    got = parsear("A las 14.30 horas", "20.30")
    colgada = got.get("14:30") == ["Pequeños poemas en prosa", "La felicidad"]
    print(f"{'ok ' if colgada else 'MAL'} cabecera no reconocida → las dos quedan juntas: {got}")
    if not colgada:
        fallos += 1

    # Una función puede tener dos horarios ("A las 15 y 21 horas").
    got = parsear("A las 15 y 21 horas", "A las 23 horas")
    dos = got.get("15:00") == ["Pequeños poemas en prosa"] and \
          got.get("21:00") == ["Pequeños poemas en prosa"]
    print(f"{'ok ' if dos else 'MAL'} doble horario en una cabecera → {got}")
    if not dos:
        fallos += 1

    # Un ciclo de más de un mes (Borzage: del 11/9 al 14/10) repite números de
    # día. Leído entero, el 13 de octubre se pisaba con el 13 de septiembre;
    # partido por mes, cada parte tiene sus propios días.
    texto = ("\nIntro del ciclo\n"
             "\nDomingo 13\nA las 15 horas\nPelícula de septiembre\n(EE.UU.; 1930)\nDirección: X.\n"
             "\nMartes 29\nA las 18 horas\nOtra de septiembre\n(EE.UU.; 1931)\nDirección: X.\n"
             "\nMartes 13\nA las 15 horas\nPelícula de octubre\n(EE.UU.; 1932)\nDirección: X.\n")
    partes = _ctba_partir_por_mes(texto)
    titulos = [sorted(e["title"] for v in parse_ctba_program_text(pt).values() for e in v) for pt in partes]
    bien = titulos == [["Otra de septiembre", "Película de septiembre"], ["Película de octubre"]]
    print(f"{'ok ' if bien else 'MAL'} ciclo de dos meses partido por mes → {titulos}")
    if not bien:
        fallos += 1

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
