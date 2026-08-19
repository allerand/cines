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
from scraper import parse_ctba_program_text

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

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
