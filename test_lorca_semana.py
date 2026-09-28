#!/usr/bin/env python3
"""
Test de la grilla semanal del Cine Lorca, sin red:

    python3 test_lorca_semana.py

El Lorca publica un cuadro de horarios por semana, de jueves a miércoles
("PROGRAMACIÓN VÁLIDA DESDE EL 24/09 AL 30/09"), pero está escaneado como
imagen en su Wix. Lo que se lee es La Nación, que expone sólo el día de hoy:
el 28/9/2026 la web mostraba las diez funciones del lunes y los martes y
miércoles en cero, con la grilla del cine ya publicada para esos días.
"""
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import scraper
from scraper import Screening, _cierre_de_la_semana, proyectar_grilla_semanal


def f(cine, title, fecha, hora):
    return Screening(cine=cine, title=title, fecha=fecha, hora=hora,
                     ticket_url="https://cinelorca.wixsite.com/cine-lorca",
                     director="Lucía Puenzo", year=2026, duration=106)


# --- La franja: de jueves a miércoles ----------------------------------------
assert _cierre_de_la_semana(date(2026, 9, 24)) == date(2026, 9, 30)   # jueves
assert _cierre_de_la_semana(date(2026, 9, 28)) == date(2026, 9, 30)   # lunes
assert _cierre_de_la_semana(date(2026, 9, 27)) == date(2026, 9, 30)   # domingo
assert _cierre_de_la_semana(date(2026, 9, 30)) == date(2026, 9, 30)   # miércoles
print("✓ la semana de programación cierra el miércoles, sea cual sea el día de hoy")


# --- Lunes: se completan martes y miércoles ----------------------------------
hoy = date(2026, 9, 28)
funciones = [f("Cine Lorca", "Pepita La Pistolera", "2026-09-28", "20:10"),
             f("Cine Lorca", "Pepita La Pistolera", "2026-09-28", "22:40")]
out = proyectar_grilla_semanal(funciones, hoy)
assert sorted((s.fecha, s.hora) for s in out) == [
    ("2026-09-28", "20:10"), ("2026-09-28", "22:40"),
    ("2026-09-29", "20:10"), ("2026-09-29", "22:40"),
    ("2026-09-30", "20:10"), ("2026-09-30", "22:40")], sorted((s.fecha, s.hora) for s in out)
print("✓ el lunes, las funciones de hoy se completan hasta el miércoles")

nueva = [s for s in out if s.fecha == "2026-09-30"][0]
assert (nueva.title, nueva.director, nueva.year, nueva.duration) == (
    "Pepita La Pistolera", "Lucía Puenzo", 2026, 106)
assert nueva.ticket_url == "https://cinelorca.wixsite.com/cine-lorca"
print("✓ la función proyectada conserva la ficha entera, no sólo el título")


# --- Miércoles: no hay nada que completar ------------------------------------
solo_hoy = [f("Cine Lorca", "La invitación", "2026-09-30", "22:00")]
assert proyectar_grilla_semanal(solo_hoy, date(2026, 9, 30)) == solo_hoy
print("✓ el miércoles la semana se termina: no se proyecta al jueves, que estrena otra grilla")


# --- Sólo los cines de grilla semanal ----------------------------------------
otros = [f("Cinépolis Recoleta", "La bola negra", "2026-09-28", "20:00"),
         f("Showcase Belgrano", "La bola negra", "2026-09-28", "20:00")]
assert proyectar_grilla_semanal(otros, hoy) == otros
print("✓ los multicines de La Nación no se proyectan: cambian la grilla el fin de semana")


# --- Lo que la fuente ya trajo manda -----------------------------------------
# Si mañana la fuente da otro horario para la misma película, no se duplica ni
# se pisa: la proyección sólo llena lo que falta.
mixtas = [f("Cine Lorca", "Tres adioses", "2026-09-28", "16:15"),
          f("Cine Lorca", "Tres adioses", "2026-09-29", "18:00")]
out = proyectar_grilla_semanal(mixtas, hoy)
martes = sorted(s.hora for s in out if s.fecha == "2026-09-29")
assert martes == ["16:15", "18:00"], martes
assert len([s for s in out if s.fecha == "2026-09-29" and s.hora == "18:00"]) == 1
print("✓ una función que la fuente ya trajo para mañana no se duplica")

# Proyectar dos veces no agrega nada (run.py la aplica por cine y al final).
assert proyectar_grilla_semanal(out, hoy) == out
print("✓ proyectar dos veces da lo mismo")

# --- La grilla del cine, transcripta en data/lorca_manual.json ---------------
# Es la que manda sobre La Nación, y se aplica a todos los días de su rango.
# El rango se arma con la semana en curso para que el test no dependa de qué
# día se corra.
GRILLA = {
    "period_start": (_cierre_de_la_semana(date.today()) - timedelta(days=6)).isoformat(),
    "period_end": _cierre_de_la_semana(date.today()).isoformat(),
    "films": [
        {"title": "Una quinta en Portugal", "times": ["14:00", "18:15"]},
        {"title": "Su propio infierno", "times": ["20:20"]},
    ],
}

with tempfile.TemporaryDirectory() as tmp:
    ruta = Path(tmp) / "lorca_manual.json"
    ruta.write_text(json.dumps(GRILLA), encoding="utf-8")
    original = scraper.LORCA_MANUAL_PATH
    scraper.LORCA_MANUAL_PATH = ruta
    try:
        funciones = scraper.scrape_lorca()
        hoy = date.today()
        dias_esperados = []
        d = hoy
        while d <= _cierre_de_la_semana(hoy):
            dias_esperados.append(d.isoformat())
            d += timedelta(days=1)
        assert sorted({s.fecha for s in funciones}) == dias_esperados
        assert len(funciones) == len(dias_esperados) * 3   # tres horarios por día
        assert {s.hora for s in funciones} == {"14:00", "18:15", "20:20"}
        print("✓ grilla del cine: los mismos horarios todos los días del rango, de hoy al miércoles")

        # Una grilla vencida no publica nada (y lo avisa en el log).
        vencida = {**GRILLA, "period_start": "2026-07-01", "period_end": "2026-07-07"}
        ruta.write_text(json.dumps(vencida), encoding="utf-8")
        assert scraper.scrape_lorca() == []
        print("✓ grilla vencida: no se publica nada, y queda La Nación")
    finally:
        scraper.LORCA_MANUAL_PATH = original

print("\nTodo OK")
