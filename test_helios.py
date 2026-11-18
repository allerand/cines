#!/usr/bin/env python3
"""
Test local del scraper del Cine Helios (cinehelios.adro.studio), sin red:

    python3 test_helios.py

Las fichas son las reales de la boletería del 18/11/2026, recortadas. La sala
tiene dos programaciones: el cineclub y el Espacio INCAA.
"""
import json
from datetime import date

import scraper
from scraper import _helios_ficha, _helios_funciones


def hora(cuando):
    return {"date": cuando + ":00.000000", "timezone_type": "3", "timezone": "UTC"}


def funcion(cuando, **extra):
    return {"id": "1", "fref": "x", "lenguaje": "Subt", "formato": "2D", "fechaHora": hora(cuando),
            "vender": "1", "mostrar": "1", "expired": False, "theaterPlay": 0, **extra}


ZEMECKIS = {"movie": {
    "nombre": "I Wanna Hold Your Hand de Robert Zemeckis", "Duracion": "104", "Condicion": ".",
    "descripcion": "Anochecer de un año agitado: \r\nCuatro películas de los cuatro de Liverpool \r\n\r\n"
                   "Cerramos nuestra temporada catorce bien arriba…\r\n\r\nMARTES 24/11 20.30HS\r\n"
                   "I Wanna Hold Your Hand, de Robert Zemeckis (1978)\r\nEn 1964, plena beatlemanía…"},
    "showtimes": [funcion("2026-11-24 20:30")]}
INTERSEX = {"movie": {
    "nombre": "INTERSEX EL CIRCULO VIOLETA", "Duracion": "93", "Condicion": "R-13",
    "descripcion": "INTERSEX: EL CÍRCULO VIOLETA\r\n\r\nFunciones: \r\n—MIÉRCOLES 18/11 18:30 HS \r\n(93’)  \r\n"
                   "Origen: Argentina\r\nClasificación: R13 C/R\r\nDirección: Teresa Martino\r\n"
                   "Sinopsis: Las personas intersex nacen…\r\n\r\nDistribuidora: MARTINO "},
    "showtimes": [funcion("2026-11-18 18:30", lenguaje="Cast")]}
LA_CASA = {"movie": {
    "nombre": "LA CASA", "Duracion": "95", "Condicion": "R-13",
    "descripcion": "LA CASA\r\n\r\nFunciones: \r\n—MARTES 17/11 18:30 HS\r\n—MIÉRCOLES 18/11 21:00 HS\r\n(95’) \r\n"
                   "Origen: Argentina\r\nClasificación: R13\r\nDirección: Gustavo Triviño\r\n"
                   "Reparto: Diego Peretti, César Troncoso\r\nSinopsis: Tras muchos años…"},
    "showtimes": [funcion("2026-11-17 18:30", expired=True), funcion("2026-11-18 21:00")]}

# --- La ficha -----------------------------------------------------------------
f = _helios_ficha(ZEMECKIS["movie"])
assert (f["title"], f["director"], f["year"], f["duration"], f["ciclo"]) == (
    "I Wanna Hold Your Hand", "Robert Zemeckis", 1978, 104, "Cineclub Helios"), f
print("✓ cineclub: el director sale del nombre, el año de la descripción, y el ciclo es Cineclub Helios")

f = _helios_ficha(INTERSEX["movie"])
assert (f["title"], f["director"], f["country"], f["year"], f["duration"], f["ciclo"]) == (
    "INTERSEX: EL CÍRCULO VIOLETA", "Teresa Martino", "Argentina", None, 93, "Cine INCAA"), f
print("✓ Cine INCAA: director y país de la ficha, título como lo escribe la descripción, sin inventar el año")

# Un " de " en el título no alcanza para partirlo: hace falta la línea del cineclub.
f = _helios_ficha({"nombre": "EL SECRETO DE SUS OJOS", "Duracion": "129",
                   "descripcion": "EL SECRETO DE SUS OJOS\nOrigen: Argentina\nDirección: Juan José Campanella"})
assert (f["title"], f["director"], f["ciclo"]) == ("EL SECRETO DE SUS OJOS", "Juan José Campanella", "Cine INCAA"), f
f = _helios_ficha({"nombre": "La noche de los lápices de Héctor Olivera", "Duracion": "",
                   "descripcion": "MARTES 1/12 20.30HS\nLa noche de los lápices, de Héctor Olivera (1986)\n…"})
assert (f["title"], f["director"], f["year"], f["duration"]) == ("La noche de los lápices", "Héctor Olivera", 1986, None), f
f = _helios_ficha({"nombre": "Película sin nada", "descripcion": ""})
assert (f["title"], f["director"], f["year"], f["ciclo"]) == ("Película sin nada", "", None, "Cine INCAA")
print("✓ el título se parte por el ' de ' que confirma la descripción, y sólo por ése")

# --- Las funciones --------------------------------------------------------------
[s] = _helios_funciones(ZEMECKIS, "dac59fce")
assert (s.cine, s.fecha, s.hora) == ("Cine Helios", "2026-11-24", "20:30")
assert s.ticket_url == "https://cinehelios.adro.studio/pelicula/45/dac59fce"
print("✓ la hora es la del afiche (20:30), aunque la API la rotule UTC")

assert [(s.fecha, s.hora) for s in _helios_funciones(LA_CASA, "x")] == [("2026-11-17", "18:30"), ("2026-11-18", "21:00")]
teatro = {"movie": {"nombre": "Obra", "descripcion": ""}, "showtimes": [funcion("2026-11-20 21:00", theaterPlay=1)]}
oculta = {"movie": {"nombre": "Peli", "descripcion": ""}, "showtimes": [funcion("2026-11-20 21:00", mostrar="0"),
                                                                    funcion("2026-11-21 21:00"), funcion("2026-11-21 21:00"),
                                                                    {"fechaHora": None}, "x"]}
assert _helios_funciones(teatro, "x") == []
assert [(s.fecha, s.hora) for s in _helios_funciones(oculta, "x")] == [("2026-11-21", "21:00")]
assert _helios_funciones({"movie": {"nombre": ""}, "showtimes": [funcion("2026-11-21 21:00")]}, "x") == []
print("✓ el teatro, las funciones ocultas, las repetidas y las rotas quedan afuera")


# --- scrape_helios ------------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 18)


CARTEL = [{"pref": "zem", "nombre": "I Wanna Hold Your Hand de Robert Zemeckis", "theaterPlay": 0},
          {"pref": "int", "nombre": "INTERSEX EL CIRCULO VIOLETA", "theaterPlay": 0},
          {"pref": "casa", "nombre": "LA CASA", "theaterPlay": 0},
          {"pref": "obra", "nombre": "Una obra de teatro", "theaterPlay": 1}]
FICHAS = {"zem": ZEMECKIS, "int": INTERSEX, "casa": LA_CASA}
_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    pedidas = []

    def _api(url, *a, **k):
        pedidas.append(url)
        if url.endswith("/nowPlaying/45"):
            return json.dumps({"status": "ok", "data": CARTEL}).encode()
        return json.dumps({"status": "ok", "data": FICHAS[url.rsplit("/", 1)[1]]}).encode()

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = _api
    r = scraper.scrape_helios()
    assert sorted((s.fecha, s.hora, s.title, s.ciclo) for s in r) == [
        ("2026-11-18", "18:30", "INTERSEX: EL CÍRCULO VIOLETA", "Cine INCAA"),
        ("2026-11-18", "21:00", "LA CASA", "Cine INCAA"),
        ("2026-11-24", "20:30", "I Wanna Hold Your Hand", "Cineclub Helios")], r
    assert not any(u.endswith("/obra") for u in pedidas) and "Cine Helios" not in scraper.FUENTES_CAIDAS
    print("✓ scrape_helios: lo que viene de las dos programaciones, sin pedir la obra de teatro")

    def _una_rota(url, *a, **k):
        if url.endswith("/casa"):
            raise TimeoutError("timed out")
        return _api(url)
    scraper.fetch_bytes = _una_rota
    r = scraper.scrape_helios()
    assert len(r) == 2 and "LA CASA" in scraper.FUENTES_CAIDAS.get("Cine Helios", "")
    print("✓ si una ficha no contesta, salen las demás y la auditoría se entera de cuál faltó")

    for cuerpo, pista in ((b"<html>mantenimiento</html>", "no contest"), (b'{"status": "error"}', "ya no devuelve")):
        scraper.FUENTES_CAIDAS.clear()
        scraper.fetch_bytes = lambda url, *a, _c=cuerpo, **k: _c
        assert scraper.scrape_helios() == []
        assert pista in scraper.FUENTES_CAIDAS.get("Cine Helios", ""), scraper.FUENTES_CAIDAS
    print("✓ si la boletería no contesta o cambia de forma, avisa en vez de dar cero")

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: b'{"status": "ok", "data": []}'
    assert scraper.scrape_helios() == [] and "Cine Helios" not in scraper.FUENTES_CAIDAS
    print("✓ una cartelera vacía no es una fuente caída")
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
