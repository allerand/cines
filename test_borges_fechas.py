#!/usr/bin/env python3
"""
Test local de las fechas, horarios y títulos del Centro Cultural Borges, sin
red (test_borges.py es el que le pega al sitio):

    python3 test_borges_fechas.py

El caso de base es el Festival Bitbang de octubre de 2026 (evento 616), que
salía con sus seis funciones el miércoles 28 a las 18, 19 y 20 h.
"""
from datetime import date, timedelta

from scraper import (_borges_funciones_from_rep, _borges_programa,
                     _borges_titulo_y_ciclo)

HOY = date(2026, 10, 19)
FIN = HOY + timedelta(weeks=9)


def funciones(rep, display="", sig_iso="", sig_hora="", hoy=HOY):
    return [(d.isoformat(), h) for d, h in
            _borges_funciones_from_rep(rep, display, sig_iso, sig_hora, hoy,
                                       hoy + timedelta(weeks=9))]


# --- Cada tramo con sus horarios ----------------------------------------------
bitbang = [("2026-10-28", "19:00"), ("2026-10-28", "20:00"),
           ("2026-10-29", "18:00"), ("2026-10-29", "19:00"),
           ("2026-10-30", "19:00"), ("2026-10-30", "20:00")]
for sep in ("\n", " / ", " | ", ", ", "<br>", " "):
    rep = sep.join(["Mie 28 oct - 19 y 20 h", "Jue 29 oct - 18 y 19 h", "Vie 30 oct - 19 y 20 h"])
    assert funciones(rep) == bitbang, (sep, funciones(rep))
print("✓ Bitbang: miércoles 19 y 20, jueves 18 y 19, viernes 19 y 20 (con cualquier separador)")

# Los formatos de un solo tramo siguen dando lo mismo que antes.
assert funciones("Mie 1 / 8 / 15 jul - 19 h", hoy=date(2026, 6, 20)) == [
    ("2026-07-01", "19:00"), ("2026-07-08", "19:00"), ("2026-07-15", "19:00")]
assert funciones("Sab 31 oct - 15, 16, 17 y 18 h") == [
    ("2026-10-31", "15:00"), ("2026-10-31", "16:00"),
    ("2026-10-31", "17:00"), ("2026-10-31", "18:00")]
assert funciones("Jue 22 oct - 14:50, 16:20, 17:50, 19:20 h") == [
    ("2026-10-22", "14:50"), ("2026-10-22", "16:20"),
    ("2026-10-22", "17:50"), ("2026-10-22", "19:20")]
assert funciones("Mar 3 mar - 19 h", hoy=date(2027, 2, 20)) == [("2027-03-03", "19:00")]
print("✓ un tramo: varias fechas, varios horarios, '14:50', y 'Mar 3 mar'")

# Lo que ya pasó no entra; el resto del festival sí.
assert funciones("Mie 28 oct - 19 y 20 h\nJue 29 oct - 18 y 19 h", hoy=date(2026, 10, 29)) == [
    ("2026-10-29", "18:00"), ("2026-10-29", "19:00")]
print("✓ los días que ya pasaron se caen solos")

# Sin día y mes en fechasRepeticiones: el camino de siempre (rango semanal o
# fecha del listado, con los horarios de la derecha del guion).
assert funciones("", display="01 NOV 2026", sig_hora="18:00:00") == [("2026-11-01", "18:00")]
assert funciones("De mie a dom - 15, 17 y 19 h", display="DE MIE A DOM")[:3] == [
    ("2026-10-21", "15:00"), ("2026-10-21", "17:00"), ("2026-10-21", "19:00")]
print("✓ sin tramos con fecha y hora, como antes (fecha del listado, rango 'de mie a dom')")


# --- El festival al ciclo -----------------------------------------------------
assert _borges_titulo_y_ciclo("FESTIVAL BITBANG: PROYECCIÓN de Cortos Latinoamericanos") == (
    "Cortos Latinoamericanos", "Festival Bitbang")
assert _borges_titulo_y_ciclo("FESTIVAL BITBANG: LA HUELLA DE ORO (PROYECCIÓN + Q&A)") == (
    "LA HUELLA DE ORO", "Festival Bitbang")
assert _borges_titulo_y_ciclo("FESTIVAL BITBANG: Retrospectiva Alberto Vázquez") == (
    "Retrospectiva Alberto Vázquez", "Festival Bitbang")
assert _borges_titulo_y_ciclo("El príncipe de Nanawa") == ("El príncipe de Nanawa", "")
assert _borges_titulo_y_ciclo("Ciclo Cuadro a Cuadro. La otra forma") == (
    "Ciclo Cuadro a Cuadro. La otra forma", "")
print("✓ 'FESTIVAL BITBANG: …' → ciclo 'Festival Bitbang' y el título sin 'Proyección de' "
      "ni '(proyección + Q&A)'")


# --- El programa de cada función, del texto del evento ------------------------
detalle = {
    "id": 616,
    "fechasRepeticiones": "Mie 28 oct - 19 y 20 h\nJue 29 oct - 18 y 19 h\nVie 30 oct - 19 y 20 h",
    "descripcion": (
        "<p>Proyección de obras en la Categoría de Cortos Latinoamericanos de BITBANG, el "
        "Festival Internacional de Animación que se realiza desde 2015 en Buenos Aires.</p>"
        "<p><strong>MIÉRCOLES 28 DE OCTUBRE</strong><br>19 h: Cortos Latinoamericanos I"
        "<br>20 h: Cortos Latinoamericanos II</p>"
        "<p><strong>JUEVES 29 DE OCTUBRE</strong><br>18 h: Cortos Latinoamericanos III"
        "<br>19 h: Cortos Latinoamericanos IV</p>"
        "<p><strong>VIERNES 30 DE OCTUBRE</strong><br>19 h: Cortos Latinoamericanos V"
        "<br>20 h: Cortos Latinoamericanos VI</p><p>Duración 60 Minutos</p>"),
}
prog = _borges_programa(detalle, HOY, FIN)
assert prog == {
    ("2026-10-28", "19:00"): "Cortos Latinoamericanos I",
    ("2026-10-28", "20:00"): "Cortos Latinoamericanos II",
    ("2026-10-29", "18:00"): "Cortos Latinoamericanos III",
    ("2026-10-29", "19:00"): "Cortos Latinoamericanos IV",
    ("2026-10-30", "19:00"): "Cortos Latinoamericanos V",
    ("2026-10-30", "20:00"): "Cortos Latinoamericanos VI",
}, prog
assert set(prog) == set(funciones(detalle["fechasRepeticiones"]))
print("✓ cada función con su programa: Cortos Latinoamericanos I a VI")

# Una descripción sin programa por horario no inventa nada.
assert _borges_programa({"descripcion": "<p>Película de 1974. Duración 127 minutos.</p>"},
                        HOY, FIN) == {}
assert _borges_programa({}, HOY, FIN) == {}
print("✓ sin programa en el texto, el título del evento")

print("\nTodo OK")
