#!/usr/bin/env python3
"""
Test local del scraper del CEA (cea.mda.gob.ar), sin red:

    python3 test_cea.py

Las funciones son las reales de la API de reservas del 18/11/2026. El sitio se
rehízo en octubre de 2026 como una aplicación que pide la programación por
JavaScript, y el scraper que leía el HTML de la home estuvo un mes en cero.
"""
import json
from datetime import date

import scraper
from scraper import _cea_funciones, _cea_inicio


def funcion(id_, starts, titulo, director, anio, dur, *, abierta=True, manual=False,
            tomadas=0, sala="Sala de Cine CEA"):
    return {"id": id_, "startsAt": starts, "room": sala, "capacity": 110, "maxPerBooking": 2,
            "notes": "", "remaining": 110 - tomadas, "taken": tomadas, "isOpen": abierta,
            "isPast": False, "closedManually": manual,
            "movie": {"id": id_, "title": titulo, "director": director, "year": anio,
                      "duration": dur, "rating": "ATP", "format": "35mm", "synopsis": "…"}}


API = [
    funcion(5, "2026-11-19T21:00:00.000Z", "Fantasmas en la Patagonia", "Claudio Remedi", 1996, 84, tomadas=12),
    funcion(6, "2026-11-21T21:00:00.000Z", "El exilio de Gardel", "Fernando «Pino» Solanas", 1986, 119,
            abierta=False, manual=True),
    funcion(8, "2026-11-21T21:00:00.000Z", "Un Cuento Chino", "Sebastián Borensztein", 2011, 93, tomadas=13),
    funcion(7, "2026-11-22T21:00:00.000Z", "La strada", "Federico Fellini", 1954, 108, tomadas=37),
]

# --- La hora ------------------------------------------------------------------
assert _cea_inicio("2026-11-19T21:00:00.000Z").strftime("%Y-%m-%d %H:%M") == "2026-11-19 18:00"
assert _cea_inicio("2026-11-20T02:30:00Z").strftime("%Y-%m-%d %H:%M") == "2026-11-19 23:30"
assert _cea_inicio("") is None and _cea_inicio(None) is None and _cea_inicio("mañana") is None
print("✓ la hora viene en UTC y sale en la de Buenos Aires (y cambia de día si hace falta)")

# --- Las funciones --------------------------------------------------------------
fs = _cea_funciones(API)
assert [(s.title, s.fecha, s.hora) for s in fs] == [
    ("Fantasmas en la Patagonia", "2026-11-19", "18:00"),
    ("Un Cuento Chino", "2026-11-21", "18:00"),
    ("La strada", "2026-11-22", "18:00")], fs
s = fs[0]
assert (s.cine, s.director, s.year, s.duration) == ("CEA", "Claudio Remedi", 1996, 84)
assert s.ticket_url == "https://cea.mda.gob.ar/funcion/5"
assert "35" not in s.title
print("✓ cada función con director, año, duración y su página de reserva; el formato no va al título")
print("✓ la que cerraron a mano sin reservas y tiene otra abierta a la misma hora no sale")

# Cerrada sola (llena, o cerrada a mano con reservas) sigue siendo una función.
llena = funcion(9, "2026-11-28T21:00:00.000Z", "La strada", "Federico Fellini", 1954, 108,
                abierta=False, tomadas=110)
cerrada = funcion(10, "2026-11-29T21:00:00.000Z", "Pizza, birra, faso", "Caetano y Stagnaro", 1998, 92,
                  abierta=False, manual=True)
con_reservas = funcion(11, "2026-11-21T21:00:00.000Z", "El exilio de Gardel", "Solanas", 1986, 119,
                       abierta=False, manual=True, tomadas=40)
assert [s.fecha for s in _cea_funciones([llena, cerrada])] == ["2026-11-28", "2026-11-29"]
assert len(_cea_funciones([con_reservas, API[2]])) == 2
otra_sala = funcion(12, "2026-11-21T21:00:00.000Z", "Corto", "Alguien", 2020, 15,
                    abierta=False, manual=True, sala="Microcine")
assert len(_cea_funciones([otra_sala, API[2]])) == 2
print("✓ una función llena, una cerrada sola, una cerrada con reservas o en otra sala se quedan")

# Datos rotos no rompen ni inventan.
raros = [None, "x", {"id": 1}, {"id": 2, "startsAt": "2026-11-30T21:00:00Z", "movie": {"title": "  "}},
         {"id": 3, "startsAt": "2026-11-30T21:00:00Z", "movie": {"title": "Sin ficha", "year": 0, "duration": None}},
         {"startsAt": "2026-12-01T21:00:00Z", "movie": {"title": "Sin id"}}]
fr = _cea_funciones(raros)
assert [(s.title, s.year, s.duration, s.director) for s in fr] == [("Sin ficha", None, None, ""), ("Sin id", None, None, "")]
assert fr[1].ticket_url == "https://cea.mda.gob.ar/"
print("✓ entradas rotas se saltean; sin año o sin id no se inventa nada")


# --- scrape_cea ---------------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 20)


_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    scraper.FUENTES_CAIDAS.clear()
    pedidas = []
    def _api(url, *a, **k):
        pedidas.append(url)
        return json.dumps(API).encode("utf-8")
    scraper.fetch_bytes = _api
    r = scraper.scrape_cea()
    assert pedidas == ["https://cea.mda.gob.ar/api/screenings"]
    assert [(s.title, s.fecha) for s in r] == [("Un Cuento Chino", "2026-11-21"), ("La strada", "2026-11-22")]
    assert "CEA" not in scraper.FUENTES_CAIDAS
    print("✓ scrape_cea: pide la API y deja afuera lo que ya pasó")

    scraper.fetch_bytes = lambda url, *a, **k: b"[]"
    assert scraper.scrape_cea() == [] and "CEA" not in scraper.FUENTES_CAIDAS
    print("✓ una lista vacía es que no hay funciones, no una fuente caída")

    for cuerpo, pista in ((b'<!doctype html><div id="root"></div>', "no contest"),
                          (b'{"error": "nope"}', "ya no devuelve"),
                          (json.dumps([{"id": 1, "fecha": "2026-11-21"}]).encode(), "no supo leer")):
        scraper.FUENTES_CAIDAS.clear()
        scraper.fetch_bytes = lambda url, *a, _c=cuerpo, **k: _c
        assert scraper.scrape_cea() == []
        assert pista in scraper.FUENTES_CAIDAS.get("CEA", ""), (pista, scraper.FUENTES_CAIDAS)
    print("✓ si la API devuelve HTML, otra cosa o funciones con otra forma, avisa a la auditoría")
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
