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

        # Dos películas que se turnan el mismo horario: cada una, sus días.
        turnos = {**GRILLA, "films": [
            {"title": "Los otros", "times": ["22:00"],
             "days": ["jueves", "sábado", "lunes", "miércoles"]},
            {"title": "Digger", "times": ["22:00"], "days": ["viernes", "Domingo", "martes"]},
            {"title": "Una quinta en Portugal", "times": ["13:55"]},
        ]}
        ruta.write_text(json.dumps(turnos), encoding="utf-8")
        funciones = scraper.scrape_lorca()
        for s in funciones:
            dia = date.fromisoformat(s.fecha).weekday()
            if s.title == "Los otros":
                assert dia in (0, 2, 3, 5), (s.fecha, s.title)
            elif s.title == "Digger":
                assert dia in (1, 4, 6), (s.fecha, s.title)
        por_dia = {}
        for s in funciones:
            por_dia.setdefault(s.fecha, []).append(s.title)
        assert all(sorted(t) in (["Digger", "Una quinta en Portugal"],
                                 ["Los otros", "Una quinta en Portugal"])
                   for t in por_dia.values()), por_dia
        print("✓ grilla del cine con días: Los otros y Digger se turnan, nunca van juntas")
    finally:
        scraper.LORCA_MANUAL_PATH = original


# --- La Nación, contrastada con el cartel --------------------------------------
# El jueves 22/10/2026 el cartel nuevo ya estaba colgado, pero no se pudo leer
# entero y el Lorca salió de La Nación, que todavía daba la semana anterior. Lo
# que sí se leyó del cartel —la semana y los horarios— alcanza para notarlo.
from scraper import LORCA_CARTEL_VISTO, contrastar_lorca_con_cartel


def g(fecha, hora, title="Digger", cine="Cine Lorca"):
    return {"cine": cine, "title_es": title, "fecha": fecha, "hora": hora}


CARTEL = {"semana": (date(2026, 10, 22), date(2026, 10, 28)), "alternados": True,
          "horas": {"13:55", "14:00", "16:00", "16:10", "18:00", "18:15", "19:50",
                    "20:00", "22:00", "22:10"}}
LORCA_CARTEL_VISTO.clear()
LORCA_CARTEL_VISTO.update(CARTEL)
otra_sala = g("2026-10-22", "13:45", "Hamnet", cine="Cinépolis Recoleta")
vieja = [g("2026-10-22", "13:45"), g("2026-10-22", "22:00"),
         g("2026-10-22", "13:40", "Una quinta en Portugal"),
         g("2026-10-23", "22:00"), otra_sala]
quedan, fuera = contrastar_lorca_con_cartel(vieja, date(2026, 10, 22))
assert quedan == [otra_sala] and fuera == 4, quedan
print("✓ La Nación con horarios que no están en el cartel de la semana: el Lorca queda vacío")

# El viernes La Nación ya está al día: sus horarios están en el cartel. Pero
# hay películas que se turnan, así que no se repite la grilla de hoy.
al_dia = [g("2026-10-23", "22:00"), g("2026-10-23", "13:55", "Una quinta en Portugal"),
          g("2026-10-24", "22:00"), g("2026-10-24", "13:55", "Una quinta en Portugal")]
quedan, fuera = contrastar_lorca_con_cartel(al_dia, date(2026, 10, 23))
assert [s["fecha"] for s in quedan] == ["2026-10-23", "2026-10-23"] and fuera == 2
print("✓ con películas que se turnan por día, La Nación vale sólo para hoy")

# Sin turnos y con el cartel confirmándola, la grilla de hoy se repite.
LORCA_CARTEL_VISTO["alternados"] = False
assert contrastar_lorca_con_cartel(al_dia, date(2026, 10, 23)) == (al_dia, 0)
# Sin nada leído del cartel (la página no cargó), sólo hoy.
LORCA_CARTEL_VISTO.clear()
quedan, fuera = contrastar_lorca_con_cartel(al_dia, date(2026, 10, 23))
assert {s["fecha"] for s in quedan} == {"2026-10-23"} and fuera == 2
print("✓ la grilla de hoy se repite hasta el miércoles sólo si el cartel la confirma")

print("\nTodo OK")
