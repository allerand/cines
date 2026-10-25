#!/usr/bin/env python3
"""
Test local de la cartelera del Cine Cosmos leída de Instagram
(_cosmos_ig_parse, scrape_cosmos_instagram y el plan B de scrape_cosmos), sin
red:

    python3 test_cosmos_instagram.py

Desde el 22/10/2026 cosmos.uba.ar contesta 503 y el Cosmos quedó en cero. La
cartelera de cada semana sale entonces del post de @cinecosmos.uba, leído con
la Business Discovery API. El post del 21/10 dice "Semana del 22 al 28 de
septiembre" aunque es de octubre, y el del 7/10 aclara días que se pisan entre
dos películas: los dos casos están acá.

El fixture cosmos_ig_media_2026-10-25.json es la respuesta real de la API del
25/10/2026 (los 12 posts que pide el scraper, con caption, fecha y link). Que
un horario sin aclaración valga para toda la semana se comparó contra lo que
publicó la web esas mismas semanas, de julio a octubre de 2026: coinciden.
"""
import io
import json
import os
import urllib.error
from datetime import date
from pathlib import Path

import scraper
from scraper import _cosmos_ig_dias, _cosmos_ig_parse, scrape_cosmos_instagram

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
RESPUESTA = json.loads((FIXTURES / "cosmos_ig_media_2026-10-25.json").read_text(encoding="utf-8"))
POSTS = {p["permalink"].rstrip("/").rsplit("/", 1)[1]: p
         for p in RESPUESTA["business_discovery"]["media"]["data"]}
VIEJAS = {p["timestamp"][:10]: p for p in json.loads(
    (FIXTURES / "cosmos_ig_carteleras_2026-08-26_09-24.json").read_text(encoding="utf-8"))}


def parsear(post, publicado: date):
    return _cosmos_ig_parse(post["caption"], publicado, post["permalink"])


def semana(desde: str, hasta: str) -> list[date]:
    a, b = date.fromisoformat(desde), date.fromisoformat(hasta)
    return [date.fromordinal(o) for o in range(a.toordinal(), b.toordinal() + 1)]


def por_pelicula(funciones):
    out = {}
    for s in funciones:
        out.setdefault((s.title, s.hora), []).append(s.fecha[8:])
    return out


# --- 21/10: el encabezado dice septiembre, el post es de octubre ------------
ini, fin, oct22 = parsear(POSTS["Dexbjv5CWmc"], date(2026, 10, 21))
assert (ini, fin) == (date(2026, 10, 22), date(2026, 10, 28)), (ini, fin)
assert len(oct22) == 8 * 7, len(oct22)
toda = ["22", "23", "24", "25", "26", "27", "28"]
assert por_pelicula(oct22) == {
    ("LA INVITACIÓN", "21:05"): toda, ("LA NEGOCIACIÓN", "19:10"): toda,
    ("TRES ADIOSES", "17:00"): toda,
    ("HANGAR ROJO", "15:25"): toda, ("HANGAR ROJO", "20:55"): toda,
    ("STOP MAKING SENSE", "16:55"): toda, ("EL GRAN FALSIFICADOR", "18:35"): toda,
    ("LOS DOMINGOS", "14:50"): toda,
}, por_pelicula(oct22)
la_inv = next(s for s in oct22 if s.title == "LA INVITACIÓN")
assert (la_inv.cine, la_inv.director, la_inv.country, la_inv.year, la_inv.duration) == (
    "Cine Cosmos", "Olivia Wilde", "Estados Unidos", 2026, 108)
assert {s.ticket_url for s in oct22} == {"https://www.instagram.com/p/Dexbjv5CWmc/"}
assert next(s for s in oct22 if s.title == "LOS DOMINGOS").director == "Alauda Ruiz de Azúa"
print("✓ 21/10: semana del 22 al 28 de octubre, 8 horarios todos los días, con su ficha")

# --- 14/10: lo que la web confirmó día por día ------------------------------
ini, fin, oct15 = parsear(POSTS["Defg3stDfZr"], date(2026, 10, 14))
assert (ini, fin) == (date(2026, 10, 15), date(2026, 10, 21))
assert len(oct15) == 56
assert next(s for s in oct15 if s.title == "STOP MAKING SENSE").country == "EE.UU."
print("✓ 14/10: del 15 al 21 de octubre, 56 funciones")

# --- 7/10: días aclarados, y dos películas en la misma sala y hora -----------
ini, fin, oct8 = parsear(POSTS["DeNYdIaDIUE"], date(2026, 10, 7))
assert (ini, fin) == (date(2026, 10, 8), date(2026, 10, 14))
pp = por_pelicula(oct8)
# "Jue, Vie, Sáb, Dom y Lun" y "Funciones especiales: lunes 12 y martes 13",
# las dos a las 20:55 en la Sala 2. El lunes 12 va la de la fecha con número;
# el miércoles 14 no lo nombra nadie y no se inventa.
assert pp[("EL AMOR QUE PERMANECE", "20:55")] == ["08", "09", "10", "11"]
assert pp[("UNA CANCIÓN PARA MI TIERRA", "20:55")] == ["12", "13"]
assert not [s for s in oct8 if s.hora == "20:55" and s.fecha == "2026-10-14"]
# Una película con dos horarios los da todos los días.
assert pp[("LOS DOMINGOS", "16:35")] == pp[("LOS DOMINGOS", "21:00")] == [
    "08", "09", "10", "11", "12", "13", "14"]
assert len(oct8) == 7 * 7 + 4 + 2
print("✓ 7/10: los días aclarados se respetan y el choque del lunes 12 se resuelve")

# --- carteleras viejas: semana corta y semana entre dos meses ----------------
ini, fin, sep24 = parsear(VIEJAS["2026-09-24"], date(2026, 9, 24))
# "⚠️ El martes 29 el cine permanecerá cerrado." cae fuera de la semana.
assert (ini, fin, len(sep24)) == (date(2026, 9, 24), date(2026, 9, 28), 8 * 5)
ini, fin, ago27 = parsear(VIEJAS["2026-08-26"], date(2026, 8, 26))
assert (ini, fin, len(ago27)) == (date(2026, 8, 27), date(2026, 9, 2), 8 * 7)
assert {s.fecha for s in ago27} == {d.isoformat() for d in semana("2026-08-27", "2026-09-02")}
print("✓ semana corta (24 al 28/9) y semana entre dos meses (27/8 al 2/9)")

# --- lo que no es una cartelera semanal ----------------------------------------
assert parsear(POSTS["DexZQ8SEbfK"], date(2026, 10, 21)) is None    # "Se suma a la..."
assert parsear(POSTS["DePyuFiFkd9"], date(2026, 10, 8)) is None     # reel del fic.uba
assert parsear(POSTS["Dd4rNb4j53p"], date(2026, 9, 29)) is None     # programa del FIC.UBA
# Un encabezado que no cae cerca de la fecha del post no se adivina.
assert parsear(POSTS["Dexbjv5CWmc"], date(2026, 8, 1)) is None
print("✓ los posts de una película o de un festival no dan funciones")

# --- aclaraciones de días ------------------------------------------------------
sem = semana("2026-10-22", "2026-10-28")       # jueves a miércoles
dias = lambda txt: [d.day for d in _cosmos_ig_dias(txt, sem)]
assert dias("") == [22, 23, 24, 25, 26, 27, 28]
assert dias("Todos los días") == [22, 23, 24, 25, 26, 27, 28]
assert dias("Jue, Vie, Sáb, Dom y Lun") == [22, 23, 24, 25, 26]
assert dias("Funciones especiales: lunes 26 y martes 27") == [26, 27]
assert dias("de jueves a domingo") == [22, 23, 24, 25]
assert dias("Sólo sábado") == [24]
assert _cosmos_ig_dias("lunes 27", sem) is None             # el 27 es martes
assert _cosmos_ig_dias("con subtítulos en inglés", sem) is None
assert _cosmos_ig_dias("lunes y 27", sem) is None           # día suelto entre fechas
assert _cosmos_ig_dias("jueves 29", sem) is None            # fuera de la semana
print("✓ aclaraciones: días sueltos, rangos, fechas con número; lo dudoso no sale")

# Un horario con una aclaración que no se entiende queda afuera; el resto no.
raro = POSTS["Dexbjv5CWmc"]["caption"].replace(
    "🕒 17:00 | Sala 1", "🕒 17:00 | Sala 1 — con presentación de la directora")
_, _, f = _cosmos_ig_parse(raro, date(2026, 10, 21))
assert len(f) == 7 * 7 and not [s for s in f if s.title == "TRES ADIOSES"]
# Un aviso de cierre adentro de la semana saca ese día entero.
cerrado = POSTS["Dexbjv5CWmc"]["caption"].replace(
    "\n\n🎬 LA INVITACIÓN", "\n⚠️ El lunes 26 el cine permanecerá cerrado.\n\n🎬 LA INVITACIÓN", 1)
_, _, f = _cosmos_ig_parse(cerrado, date(2026, 10, 21))
assert len(f) == 8 * 6 and not [s for s in f if s.fecha == "2026-10-26"]
print("✓ aclaración ilegible y aviso de cierre: sólo se pierde lo que tocan")


# --- scrape_cosmos_instagram, con la respuesta de la API -----------------------
pedidos = []


def graph_falso(path, params):
    pedidos.append((path, params))
    return RESPUESTA


graph_real = scraper._graph_get
scraper._graph_get = graph_falso
os.environ["IG_ACCESS_TOKEN"] = "token-de-prueba"
os.environ.pop("IG_USER_ID", None)

hoy = scrape_cosmos_instagram(2, today=date(2026, 10, 25))
assert {s.fecha for s in hoy} == {"2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"}
assert len(hoy) == 8 * 4
path, params = pedidos[-1]
assert path == "17841418915611224" and params["access_token"] == "token-de-prueba"
assert "business_discovery.username(cinecosmos.uba)" in params["fields"]
# El miércoles 21 todavía es la semana del post del 14/10; desde el jueves, la nueva.
mie = scrape_cosmos_instagram(2, today=date(2026, 10, 21))
assert {s.title for s in mie if s.fecha == "2026-10-21"} >= {"FRANZ", "EL BOSCO, EL JARDÍN DE LOS SUEÑOS"}
assert {s.ticket_url for s in mie if s.fecha == "2026-10-21"} == {"https://www.instagram.com/p/Defg3stDfZr/"}
assert {s.ticket_url for s in mie if s.fecha > "2026-10-21"} == {"https://www.instagram.com/p/Dexbjv5CWmc/"}
assert len(mie) == 8 + 8 * 7
# Si el último post ya es viejo, no hay funciones (no se estira la semana).
assert scrape_cosmos_instagram(2, today=date(2026, 10, 29)) == []
print("✓ scrape_cosmos_instagram: cada día sale del post más nuevo que lo cubre")


# --- el error de Meta sube, el token no ----------------------------------------
def urlopen_190(url, timeout=0):
    raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(json.dumps(
        {"error": {"message": "Error validating access token", "code": 190}}).encode()))


urlopen_real = scraper.urllib.request.urlopen
scraper.urllib.request.urlopen = urlopen_190
try:
    graph_real("17841418915611224", {"fields": "x", "access_token": "token-secreto"})
    raise AssertionError("tenía que fallar")
except RuntimeError as e:
    assert "190" in str(e) and "Error validating access token" in str(e), e
    assert "token-secreto" not in str(e), e
finally:
    scraper.urllib.request.urlopen = urlopen_real
print("✓ un token vencido avisa con el código de Meta, sin mostrar el token")


# --- el plan B de scrape_cosmos -------------------------------------------------
def web_caida(url):
    raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)


fila_ig = scraper.Screening(cine="Cine Cosmos", title="HANGAR ROJO", fecha="2026-10-25",
                            hora="15:25", ticket_url="https://www.instagram.com/p/Dexbjv5CWmc/")
scraper.fetch_html = web_caida

scraper.scrape_cosmos_instagram = lambda semanas=2: [fila_ig]
scraper.FUENTES_CAIDAS.clear()
assert scraper.scrape_cosmos(2) == [fila_ig]
motivo = scraper.FUENTES_CAIDAS["Cine Cosmos"]
assert "cosmos.uba.ar no contesta" in motivo and "503" in motivo and "Instagram" in motivo, motivo


def sin_token(semanas=2):
    raise RuntimeError("falta IG_ACCESS_TOKEN")


scraper.scrape_cosmos_instagram = sin_token
scraper.FUENTES_CAIDAS.clear()
assert scraper.scrape_cosmos(2) == []
assert "Instagram tampoco: falta IG_ACCESS_TOKEN" in scraper.FUENTES_CAIDAS["Cine Cosmos"]

scraper.scrape_cosmos_instagram = lambda semanas=2: []
scraper.FUENTES_CAIDAS.clear()
assert scraper.scrape_cosmos(2) == []
assert "no hay cartelera de esta semana" in scraper.FUENTES_CAIDAS["Cine Cosmos"]

# Con la web viva, Instagram ni se consulta y la fuente no queda marcada.
consultas = []
scraper.scrape_cosmos_instagram = lambda semanas=2: consultas.append(1) or [fila_ig]
scraper.fetch_html = lambda url: scraper.BeautifulSoup(
    '<div class="card"><a href="/pelicula?idPelicula=431"></a>'
    '<h4 class="card-title">El Bosco, el jardín de los sueños</h4>'
    '<div class="card-footer"><p>Ju Vi Sá Do Lu Ma Mi | 14:55</p></div></div>', "html.parser")
scraper.FUENTES_CAIDAS.clear()
web = scraper.scrape_cosmos(2)
assert web and not consultas and "Cine Cosmos" not in scraper.FUENTES_CAIDAS
assert {s.ticket_url for s in web} == {"https://cosmos.uba.ar/pelicula?idPelicula=431"}
print("✓ scrape_cosmos: la web manda; sin web, Instagram, y la fuente queda marcada")

print("\nTodo OK")
