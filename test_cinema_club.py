#!/usr/bin/env python3
"""
Test local del scraper de The Cinema Club Company (cinemaclubcompany.com), sin
red:

    python3 test_cinema_club.py

Los eventos son los reales de la API de Fanz del 18/11/2026, recortados. Son
tres sedes (Palermo, Recoleta, Lomas de Zamora) y cada una es una sala.
"""
import json
from datetime import date

import scraper
from scraper import _ccc_funciones, _ccc_sede, _ccc_titulo


def evento(id_, titulo, inicio, lugar, categoria="", **extra):
    return {"id": id_, "title": titulo, "slug": f"{id_}-slug", "isExternal": False,
            "Dates": [{"start": inicio, "isSoldOut": False}],
            "Location": {"locationName": lugar, "isOnline": False},
            "Category": {"name": categoria or lugar}, **extra}


RECOLETA = "AURA SKY BAR - RECOLETA"
LOMAS = "LA PANERA ROSA - LOMAS DE ZAMORA (LOMITAS STREET)"
PALERMO = "PANI PIZZA FEROZ - PALERMO"

# --- El título ----------------------------------------------------------------
assert _ccc_titulo("BEETLEJUICE (1988) - MIERCOLES  18/11 - 19:45hs") == ("Beetlejuice", 1988)
assert _ccc_titulo("CRAZY, STUPID, LOVE. (2011) - SABADO  28/11 - 19:45hs") == ("Crazy, Stupid, Love.", 2011)
assert _ccc_titulo("ROMEO + JULIET (1996) - MIERCOLES  18/11 - 21:45hs") == ("Romeo + Juliet", 1996)
assert _ccc_titulo("EL EXTRAÑO MUNDO DE JACK  (1993) - DOMINGO 22/11 - 19:45hs") == ("El Extraño Mundo de Jack", 1993)
assert _ccc_titulo("ETERNO RESPLANDOR DE UNA MENTE.. - SABADO 21/11 - 19:45hs") == ("Eterno Resplandor de una Mente", None)
assert _ccc_titulo("SPIDER-MAN (2002) - SÁBADO 5/12 - 19:45hs") == ("Spider-man", 2002)
assert _ccc_titulo("") == ("", None)
assert _ccc_titulo("LA LA LAND (2016) - LUNES 30/11 - 21:45hs") == ("La La Land", 2016)
assert _ccc_titulo("LA HISTORIA SIN FIN (1984) - MIERCOLES  25/11 - 19:45hs") == ("La Historia sin Fin", 1984)
assert _ccc_titulo("THE LORD OF THE RINGS (2001) - LUNES 7/12 - 19:45hs") == ("The Lord of the Rings", 2001)
assert _ccc_titulo("Amélie (2001) - LUNES 7/12 - 19:45hs") == ("Amélie", 2001)
print("✓ título: sale el año, se va la cola del día y la hora, y un guion del título no lo corta")
print("✓ el título gritado se baja acá, con el nombre que usa la sala (no el de España)")

# --- La sede ------------------------------------------------------------------
assert _ccc_sede(evento(1, "X", "", RECOLETA)) == "Cinema Club Recoleta"
assert _ccc_sede(evento(1, "X", "", LOMAS)) == "Cinema Club Lomas de Zamora"
assert _ccc_sede(evento(1, "X", "", PALERMO, "Pani Pizza Feroz - Palermo Soho")) == "Cinema Club Palermo"
assert _ccc_sede(evento(1, "X", "", "BAR NUEVO", "Pani Pizza Feroz - Palermo Soho")) == "Cinema Club Palermo"
assert _ccc_sede(evento(1, "X", "", "TERRAZA - BELGRANO")) == ""
print("✓ sede: por el barrio del lugar o de la categoría; un lugar nuevo no se adivina")

# --- Las funciones --------------------------------------------------------------
EVENTOS = [
    evento(183984, "BEETLEJUICE (1988) - MIERCOLES  18/11 - 19:45hs", "2026-11-18T22:45:00.000Z", RECOLETA),
    evento(184023, "DONNIE DARKO (2001) - MIERCOLES  18/11 - 21:45hs", "2026-11-19T00:45:00.000Z", RECOLETA),
    evento(182500, "ETERNO RESPLANDOR DE UNA MENTE.. - SABADO 21/11 - 19:45hs", "2026-11-21T22:45:00.000Z", PALERMO),
    evento(184053, "ETERNO RESPLANDOR DE UNA MENTE.. (2004) - DOMINGO 22/11 - 21:45hs", "2026-11-23T00:45:00.000Z", LOMAS),
    evento(182498, "LABERINTO (1986) - DOMINGO 29/11 - 19:45hs", "2026-11-29T22:45:00.000Z", PALERMO),
    evento(184049, "LABERINTO (1986) - DOMINGO 29/11 - 19:45hs", "2026-11-29T22:45:00.000Z", LOMAS),
]
fs, sin_sede = _ccc_funciones(EVENTOS)
assert sin_sede == []
assert [(s.cine, s.title, s.fecha, s.hora, s.year) for s in fs] == [
    ("Cinema Club Recoleta", "Beetlejuice", "2026-11-18", "19:45", 1988),
    ("Cinema Club Recoleta", "Donnie Darko", "2026-11-18", "21:45", 2001),
    ("Cinema Club Palermo", "Eterno Resplandor de una Mente", "2026-11-21", "19:45", 2004),
    ("Cinema Club Lomas de Zamora", "Eterno Resplandor de una Mente", "2026-11-22", "21:45", 2004),
    ("Cinema Club Palermo", "Laberinto", "2026-11-29", "19:45", 1986),
    ("Cinema Club Lomas de Zamora", "Laberinto", "2026-11-29", "19:45", 1986)], fs
assert fs[0].ticket_url == "https://www.cinemaclubcompany.com/event/183984-slug"
print("✓ la hora sale de la fecha en UTC (22:45Z = 19:45), y la de las 21:45 no se pasa al día siguiente")
print("✓ el mismo título sin año toma el de su otra función; la misma película en dos sedes son dos funciones")

raros = [None, "x", {"title": "SIN FECHA (1990) - LUNES 1/12 - 20hs", "Location": {"locationName": RECOLETA}, "Dates": []},
         evento(1, "AFUERA (2000) - LUNES 1/12 - 20hs", "2026-12-01T23:00:00.000Z", RECOLETA, isExternal=True),
         evento(2, "FECHA ROTA (2000) - LUNES 1/12 - 20hs", "pronto", RECOLETA),
         evento(3, "OTRO BAR (2000) - LUNES 1/12 - 20hs", "2026-12-01T23:00:00.000Z", "TERRAZA - BELGRANO"),
         EVENTOS[0], EVENTOS[0]]
fr, sin_sede = _ccc_funciones(raros)
assert [(s.title, s.fecha) for s in fr] == [("Beetlejuice", "2026-11-18")] and sin_sede == ["TERRAZA - BELGRANO"]
print("✓ eventos rotos, externos o repetidos quedan afuera; un lugar desconocido se informa, no se inventa")


# --- scrape_cinema_club -------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 19)


_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    pedidas = []

    def _api(url, *a, **k):
        pedidas.append(url)
        off = int(url.split("offset=")[1].split("&")[0])
        return json.dumps({"count": len(EVENTOS), "events": EVENTOS[off:off + 4]}).encode()

    scraper.CCC_PAGINA, _pag = 4, scraper.CCC_PAGINA
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = _api
    r = scraper.scrape_cinema_club()
    assert len(pedidas) == 2 and "offset=0&limit=4&hostname=www.cinemaclubcompany.com" in pedidas[0] and "offset=4" in pedidas[1]
    assert [s.title for s in r] == ["Eterno Resplandor de una Mente"] * 2 + ["Laberinto"] * 2, r
    assert not scraper.FUENTES_CAIDAS
    print("✓ scrape_cinema_club: pide página por página hasta juntar todas, y deja afuera lo que ya pasó")

    def _corta(url, *a, **k):
        if "offset=4" in url:
            raise TimeoutError("timed out")
        return _api(url)
    scraper.fetch_bytes = _corta
    assert scraper.scrape_cinema_club() == []
    assert set(scraper.FUENTES_CAIDAS) == set(scraper.CCC_SEDES.values())
    print("✓ si una página falla no publica media grilla: avisa por las tres sedes")

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: json.dumps({"count": 1, "events": [raros[5]]}).encode()
    assert scraper.scrape_cinema_club() == []
    assert "TERRAZA - BELGRANO" in scraper.FUENTES_CAIDAS["Cinema Club Palermo"]
    print("✓ una sede nueva queda dicha en la auditoría")

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: b'{"count": 0, "events": []}'
    assert scraper.scrape_cinema_club() == [] and not scraper.FUENTES_CAIDAS
    print("✓ sin funciones publicadas no es una fuente caída")
    scraper.CCC_PAGINA = _pag
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
