#!/usr/bin/env python3
"""
Test local del scraper de Cineclub Turdera (Instagram, @cineclubturdera), sin
red:

    python3 test_turdera.py

Los textos son los de sus posts de septiembre a noviembre de 2026, recortados
en la reseña, como los devolvió la Business Discovery API el 18/11/2026.
"""
import os
from datetime import date

import scraper
from scraper import _turdera_ficha, _turdera_funciones, _turdera_post

SEMANAL = """VIERNES 20/11

Stéphane (Timothée Hochet y Lucas Pastor, Francia, 2023, 78min). Comedia negra. Suspenso. ¿Falso? documental, terror.

Un cineasta independiente y principiante conoce a un técnico en explosivos de lo más simpático y excéntrico…

Este viernes 20 de NOVIEMBRE
en el inquietante salón del Rotary Club.
21hs buffet
22hs proyección
San Luis 369, Turdera
$3.000

#cineenturdera #cineclubturdera #stéphane"""

MENSUAL = """: Noviembre en CiNe Club TurDeRa

Viernes 6/11: Bad Apples (Jonatan Etzler, Inglaterra, 2025). Thriller. Comedia negra.
Una joven docente de primaria debe barajar a un alumnito muy violento y mal llevado.

Viernes 13/11: Milán, calibre 9 (Fernando Di Leo, Italia, 1972). Acción. Thriller. Poliziesco.
Al salir de la cárcel, el ex delincuente Ugo Piazza es acorralado por la mafia.

Viernes 20/11: Stéphane (Timothee Hochet y Lucas Pastor, Francia, 2023). Comedia negra. Suspenso.
Un cineasta independiente contrata a un técnico en explosivos.

Viernes 27/11: El Dentista (Brian Yuzna, EEUU, 1996). Terror. Comedia.
Un exitoso dentista entra en crisis.

Todos los Viernes de Octubre en el misterioso salón del Rotary Club
San Luis 369, Turdera.
21hs BUFFET / 22hs PELÍCULA
puerta $3.000"""

CORMAN = """VIERNES 23/10

El falso escultor ("A bucket of blood", Roger Corman, EEUU, 1959). Comedia negra. Suspenso.

Un tímido mozo quiere ser artista…

21hs  buffet
22hs proyección"""

SIN_HORA = """VIERNES 25/9

Poltergeist (Tobe Hooper, EEUU, 1982). Terror.

Este viernes en el Rotary Club.
21hs buffet"""

# --- La ficha -----------------------------------------------------------------
assert _turdera_ficha("Timothée Hochet y Lucas Pastor, Francia, 2023, 78min") == {
    "year": 2023, "country": "Francia", "director": "Timothée Hochet y Lucas Pastor",
    "duration": 78, "original_title": ""}
assert _turdera_ficha('"A bucket of blood", Roger Corman, EEUU, 1959') == {
    "year": 1959, "country": "EEUU", "director": "Roger Corman", "duration": None,
    "original_title": "A bucket of blood"}
assert _turdera_ficha("Le Samourai, Jean-Pierre Melville, FRANCIA, 1967")["original_title"] == "Le Samourai"
assert _turdera_ficha("Fernando Di Leo, Italia, 1972")["director"] == "Fernando Di Leo"
assert _turdera_ficha("Fernando Di Leo, 1972") is None
assert _turdera_ficha("una gran película") is None
print("✓ ficha: director, país y año; el título original de adelante y la duración de atrás")

# --- Un post ------------------------------------------------------------------
[s] = _turdera_post(SEMANAL, date(2026, 11, 17), "https://www.instagram.com/p/Df2Aig_kWPD/")
assert (s.cine, s.title, s.fecha, s.hora) == ("Cineclub Turdera", "Stéphane", "2026-11-20", "22:00")
assert (s.director, s.country, s.year, s.duration) == ("Timothée Hochet y Lucas Pastor", "Francia", 2023, 78)
assert s.ticket_url == "https://www.instagram.com/p/Df2Aig_kWPD/"
print("✓ post de la semana: la película es el renglón que sigue al día, y la hora es la de la proyección, no la del buffet")

mes = _turdera_post(MENSUAL, date(2026, 11, 3))
assert [(s.title, s.fecha, s.hora, s.director, s.year) for s in mes] == [
    ("Bad Apples", "2026-11-06", "22:00", "Jonatan Etzler", 2025),
    ("Milán, calibre 9", "2026-11-13", "22:00", "Fernando Di Leo", 1972),
    ("Stéphane", "2026-11-20", "22:00", "Timothee Hochet y Lucas Pastor", 2023),
    ("El Dentista", "2026-11-27", "22:00", "Brian Yuzna", 1996)], mes
print("✓ post del mes: una función por renglón, con la coma del título adentro ('Milán, calibre 9')")

[s] = _turdera_post(CORMAN, date(2026, 10, 19))
assert (s.title, s.original_title, s.director) == ("El falso escultor", "A bucket of blood", "Roger Corman")
assert _turdera_post(SIN_HORA, date(2026, 9, 22)) == []
assert _turdera_post("JUEVES 20/11\n\nStéphane (X, Francia, 2023).\n22hs proyección", date(2026, 11, 17)) == []
assert _turdera_post("VIERNES 20/11\n\nUna sorpresa\n\n22hs proyección", date(2026, 11, 17)) == []
assert _turdera_post("¡Gracias a todos los que vinieron el viernes!", date(2026, 11, 17)) == []
assert _turdera_post("", date(2026, 11, 17)) == []
print("✓ sin hora de proyección, con el día de la semana corrido o sin ficha, el post no da funciones")

# Diciembre anunciado en diciembre, enero anunciado en diciembre.
[s] = _turdera_post("VIERNES 8/1\n\nAlgo (Alguien, Italia, 1970).\n22hs proyección", date(2026, 12, 29))
assert s.fecha == "2027-01-08"
print("✓ el año sale de la fecha del post: enero anunciado en diciembre es del año que viene")


# --- Todos los posts ----------------------------------------------------------
def post(texto, cuando, id_):
    return {"caption": texto, "timestamp": cuando, "permalink": f"https://www.instagram.com/p/{id_}/"}


POSTS = [
    post(SEMANAL, "2026-11-17T13:11:00+0000", "sem3"), post(SEMANAL, "2026-11-17T13:10:00+0000", "sem2"),
    post(SEMANAL, "2026-11-17T13:04:00+0000", "sem1"),
    post(MENSUAL, "2026-11-03T03:39:00+0000", "mes2"), post(MENSUAL, "2026-11-03T03:36:00+0000", "mes1"),
    post(CORMAN, "2026-10-19T15:00:00+0000", "corman"), post(SIN_HORA, "2026-09-22T15:00:00+0000", "polter"),
    {"timestamp": "roto"}, None,
]
fs = _turdera_funciones(POSTS)
assert [(s.fecha, s.title) for s in fs] == [
    ("2026-10-23", "El falso escultor"), ("2026-11-06", "Bad Apples"), ("2026-11-13", "Milán, calibre 9"),
    ("2026-11-20", "Stéphane"), ("2026-11-27", "El Dentista")], fs
stephane = fs[3]
assert stephane.ticket_url.endswith("/sem3/") and stephane.duration == 78
assert stephane.director == "Timothée Hochet y Lucas Pastor"
print("✓ el mismo post subido tres veces da una sola función, y por cada viernes manda el post más nuevo")


# --- scrape_turdera -----------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 18)


_date, _graph = scraper.date, scraper._graph_get
_env = {k: os.environ.pop(k, None) for k in ("IG_ACCESS_TOKEN", "IG_USER_ID")}
scraper.date = _Hoy
try:
    scraper.FUENTES_CAIDAS.clear()
    assert scraper.scrape_turdera() == []
    assert "IG_ACCESS_TOKEN" in scraper.FUENTES_CAIDAS["Cineclub Turdera"]
    print("✓ sin token no inventa nada y lo dice")

    os.environ["IG_ACCESS_TOKEN"] = "token-de-prueba"
    pedidos = []

    def _api(path, params, **k):
        pedidos.append((path, params))
        return {"business_discovery": {"media": {"data": POSTS}}}
    scraper.FUENTES_CAIDAS.clear()
    scraper._graph_get = _api
    r = scraper.scrape_turdera()
    assert [(s.fecha, s.title) for s in r] == [("2026-11-20", "Stéphane"), ("2026-11-27", "El Dentista")], r
    assert pedidos[0][0] == scraper.COSMOS_IG_CONSULTA and "username(cineclubturdera)" in pedidos[0][1]["fields"]
    assert not scraper.FUENTES_CAIDAS
    print("✓ scrape_turdera: pide los posts a Business Discovery y deja lo que viene")

    def _error(path, params, **k):
        raise RuntimeError("Graph API 400: Error validating access token (code 190)")
    scraper._graph_get = _error
    assert scraper.scrape_turdera() == []
    assert "code 190" in scraper.FUENTES_CAIDAS["Cineclub Turdera"]
    assert "token-de-prueba" not in scraper.FUENTES_CAIDAS["Cineclub Turdera"]

    scraper.FUENTES_CAIDAS.clear()
    scraper._graph_get = lambda path, params, **k: {"business_discovery": {"media": {"data": [post("Feliz año", "2026-11-17T13:11:00+0000", "x")]}}}
    assert scraper.scrape_turdera() == [] and "formato" in scraper.FUENTES_CAIDAS["Cineclub Turdera"]
    print("✓ si Meta rechaza el token o los posts cambian de formato, avisa a la auditoría (sin mostrar el token)")
finally:
    scraper.date, scraper._graph_get = _date, _graph
    for k, v in _env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
