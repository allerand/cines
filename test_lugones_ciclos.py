#!/usr/bin/env python3
"""
Test de scrape_lugones cuando no puede leer la página de un ciclo, sin red ni
navegador:

    python3 test_lugones_ciclos.py

El 15/11/2026 el runner no pudo leer ninguna página de ciclo del CTBA y el
scraper publicó el nombre de cada ciclo como si fuera una película: "Homenaje
a John Huston" y "Herzog-Kinski: enemigo mío" con ciclo "Estreno", en las
fechas de entradasba, y cuatro ciclos más como filas "Sin fecha". Lo que se
prueba: que un ciclo que no se pudo leer no sale (y la fuente queda marcada),
que los estrenos siguen saliendo, y que un ciclo legible sale con sus
películas.
"""
import asyncio
import json
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

import scraper

LUGONES = "Sala Leopoldo Lugones"
HUSTON = "https://complejoteatral.gob.ar/produccion/homenaje-a-john-huston/"
HERZOG = "https://complejoteatral.gob.ar/produccion/herzog-kinski-enemigo-mio/"
TREN = "https://complejoteatral.gob.ar/produccion/el-tren-fluvial-2/"
FINLANDIA = "https://complejoteatral.gob.ar/produccion/desde-finlandia-con-amor-3/"
LUBITSCH = "https://complejoteatral.gob.ar/produccion/cinco-tardes-con-ernst-lubitsch/"
EBA_HUSTON = "https://entradasba.buenosaires.gob.ar/evento/b1a10d07"
EBA_HERZOG = "https://entradasba.buenosaires.gob.ar/evento/c0cd25cc"
EBA_TREN = "https://entradasba.buenosaires.gob.ar/evento/2d4ff5e7"


def tarjeta(titulo, ver, compra=""):
    boton = f'<a class="button buy" href="{compra}">Comprar</a>' if compra else ""
    return (f'<div class="list-item-programacion"><span class="category">Cine</span>'
            f'<span class="place">{LUGONES}</span><h2 class="mango-grotesque">{titulo}</h2>'
            f'<a href="{ver}">Ver más</a>{boton}</div>')


HOME = "<html><body>" + "".join([
    tarjeta("Homenaje a John Huston", HUSTON, EBA_HUSTON),
    tarjeta("Herzog-Kinski: enemigo mío", HERZOG, EBA_HERZOG),
    tarjeta("El tren fluvial", TREN, EBA_TREN),
    tarjeta("Desde Finlandia con amor", FINLANDIA),
    tarjeta("Cinco tardes con Ernst Lubitsch", LUBITSCH),
]) + "</body></html>"

RELLENO = ("El ciclo está organizado por el Complejo Teatral de Buenos Aires, "
           "dependiente del Ministerio de Cultura de la Ciudad. " * 4)

# Un ciclo legible, con el formato real de las páginas del CTBA.
TEXTO_FINLANDIA = f"""Desde Finlandia con amor – Complejo Teatral de Buenos Aires
Desde Finlandia con amor
Del jueves 26 al sábado 28 de noviembre se llevará a cabo un ciclo denominado Desde Finlandia con amor.
{RELLENO}
Jueves 26
A las 18 horas
Je’vida
(Finlandia, 2023)
Dirección: Katja Gauriloff.
(90′; DCP).
A las 20.30 horas
Orenda
(Finlandia, 2025)
Dirección: Pirjo Honkasalo.
(100′; DCP).
"""

# La página del Herzog-Kinski si el CTBA cambiara el formato del programa: se
# presenta como ciclo, pero el parser no encuentra ninguna función.
TEXTO_HERZOG_NUEVO = f"""Herzog-Kinski: enemigo mío – Complejo Teatral de Buenos Aires
Herzog-Kinski: enemigo mío
El ciclo está integrado por los cinco largometrajes dirigidos por Werner Herzog y protagonizados por Klaus Kinski.
{RELLENO}
12/11 · 21 h · Aguirre, la ira de Dios
13/11 · 18 h · Cobra verde
"""

# El estreno: sin la palabra ciclo, y con "a las 21 horas" dos veces en la
# prosa, como la página real de El tren fluvial.
TEXTO_TREN = """El tren fluvial – Complejo Teatral de Buenos Aires
El tren fluvial
El viernes 20 y el domingo 22 de noviembre, a las 21 horas, tendrán lugar dos nuevas funciones de El tren fluvial, el largometraje de Lorenzo Ferro y Lucas A. Vignale que tuvo su lanzamiento mundial en el Festival de Berlín. A las 21 horas, en la Sala Leopoldo Lugones del Teatro San Martín.
Título original: El tren fluvial Argentina 2026 Castellano Color 90' – DCP
Dirección y guion: Lorenzo Ferro, Lucas A. Vignale Producción: Fundación Cinemateca
"""

# Lo que contesta la ver por HTTP (None = no se pudo) y lo que muestra el
# navegador. Un desafío anti-bots o una página a medio cargar no nombra el evento.
TEXTOS = {HUSTON: None, HERZOG: TEXTO_HERZOG_NUEVO, TREN: TEXTO_TREN,
          FINLANDIA: TEXTO_FINLANDIA, LUBITSCH: None}
DESAFIO = "<html><body>Just a moment... Checking your browser before accessing.</body></html>"


def entradasba(*fechas):
    return "<html><body>" + "".join(
        f'<div class="fecha-card"><div class="dia-numero">{d}</div>'
        f'<div class="dia-nombre">NOVIEMBRE</div><div class="horario-unico">{h} h.</div></div>'
        for d, h in fechas) + "</body></html>"


NAVEGADOR = {
    EBA_HUSTON: entradasba(("15", "15:00"), ("17", "15:00"), ("17", "18:00"), ("18", "15:00")),
    EBA_HERZOG: entradasba(("15", "18:00"), ("15", "21:00"), ("19", "21:00"), ("21", "18:00")),
    EBA_TREN: entradasba(("20", "21:00"), ("22", "21:00")),
}


class PaginaFalsa:
    def __init__(self):
        self.url = None
        self.visitas = []

    async def goto(self, url, **k):
        self.url = url
        self.visitas.append(url)

    async def wait_for_timeout(self, ms):
        pass

    async def content(self):
        return NAVEGADOR.get(self.url, DESAFIO)


class HoyFijo(scraper.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 15)


tmp = Path(tempfile.mkdtemp())
scraper.CTBA_EVENTOS_PATH = tmp / "ctba_eventos.json"
scraper.date = HoyFijo
scraper.fetch_html = lambda url: BeautifulSoup(HOME, "html.parser")
scraper.fetch_ctba_ver_page_sync = lambda url: TEXTOS.get(url)


def correr():
    scraper.FUENTES_CAIDAS.clear()
    pagina = PaginaFalsa()
    fs = asyncio.run(scraper.scrape_lugones(pagina))
    return fs, pagina


fs, pagina = correr()
filas = sorted((s.fecha, s.hora, s.title, s.ciclo) for s in fs)

# 1. Ningún ciclo sale como película, ni con fecha ni "Sin fecha".
nombres = {"Homenaje a John Huston", "Herzog-Kinski: enemigo mío",
           "Desde Finlandia con amor", "Cinco tardes con Ernst Lubitsch"}
assert not [f for f in filas if f[2] in nombres], filas
assert not [f for f in filas if f[0] == "Sin fecha"], filas
print("✓ un ciclo que no se pudo leer no sale como película (ni con fecha ni 'Sin fecha')")

# 2. Pero se intentó con el navegador antes de darlo por perdido.
assert HUSTON in pagina.visitas and LUBITSCH in pagina.visitas, pagina.visitas
# ...y a entradasba no se fue a buscar fechas para un ciclo sin programa.
assert EBA_HUSTON not in pagina.visitas and EBA_HERZOG not in pagina.visitas, pagina.visitas
print("✓ antes de dejarlo afuera, la página se pide también con el navegador")

# 3. La fuente queda marcada, con cada ciclo y por qué.
motivo = scraper.FUENTES_CAIDAS.get("Sala Lugones", "")
assert "no se pudo leer «Homenaje a John Huston»" in motivo, motivo
assert "no se pudo leer «Cinco tardes con Ernst Lubitsch»" in motivo, motivo
assert "parser no entendió el programa de «Herzog-Kinski: enemigo mío»" in motivo, motivo
print("✓ la fuente queda marcada como caída, con cada ciclo que faltó")

# 4. El estreno sigue saliendo, aunque su página diga "a las 21 horas" dos veces.
assert ("2026-11-20", "21:00", "El tren fluvial", "Estreno") in filas, filas
assert ("2026-11-22", "21:00", "El tren fluvial", "Estreno") in filas, filas
print("✓ el estreno sale igual, con las fechas de entradasba")

# 5. El ciclo legible sale con sus películas.
assert ("2026-11-26", "18:00", "Je’vida", "Desde Finlandia con amor") in filas, filas
assert ("2026-11-26", "20:30", "Orenda", "Desde Finlandia con amor") in filas, filas
assert len(filas) == 4, filas
print("✓ un ciclo legible sale película por película")

# 6. Si todo se lee, no queda nada marcado.
TEXTOS.update({HUSTON: TEXTO_FINLANDIA.replace("Desde Finlandia con amor", "Homenaje a John Huston"),
               HERZOG: TEXTO_FINLANDIA.replace("Desde Finlandia con amor", "Herzog-Kinski: enemigo mío"),
               LUBITSCH: TEXTO_TREN.replace("El tren fluvial", "Cinco tardes con Ernst Lubitsch")})
fs, _ = correr()
assert "Sala Lugones" not in scraper.FUENTES_CAIDAS, scraper.FUENTES_CAIDAS
assert not [s for s in fs if s.fecha == "Sin fecha"], fs
print("✓ con todas las páginas legibles no queda nada marcado")

# 7. Un ciclo que salió del listado (memoria de eventos) y ya no carga no marca
#    la fuente: es el ciclo que terminó, no la fuente caída.
scraper.CTBA_EVENTOS_PATH.write_text(json.dumps({
    "https://complejoteatral.gob.ar/produccion/ciclo-viejo/": {
        "titulo": "Ciclo viejo", "ticket_url": "", "visto": "2026-11-10"}}), encoding="utf-8")
fs, _ = correr()
assert "Sala Lugones" not in scraper.FUENTES_CAIDAS, scraper.FUENTES_CAIDAS
print("✓ un ciclo viejo que ya no carga no cuenta como fuente caída")

# 8. El año de un ciclo cuyo programa no lo dice. El de diciembre leído en
#    noviembre se iba a 2027 (y afuera de la cartelera) hasta el 1/12.
D = scraper.date
assert scraper._ctba_anio_del_mes(12, D(2026, 11, 15)) == 2026     # Lubitsch, 4 al 13/12
assert scraper._ctba_anio_del_mes(11, D(2026, 10, 20)) == 2026     # el mes que viene
assert scraper._ctba_anio_del_mes(9, D(2026, 10, 3)) == 2026       # Borzage, ya empezado
assert scraper._ctba_anio_del_mes(1, D(2026, 12, 10)) == 2027      # enero, leído en diciembre
assert scraper._ctba_anio_del_mes(12, D(2027, 1, 5)) == 2026       # diciembre, leído en enero
print("✓ el año del ciclo: el mes que viene es de este año, enero leído en diciembre del próximo")

TEXTOS[LUBITSCH] = f"""Cinco tardes con Ernst Lubitsch – Complejo Teatral de Buenos Aires
Cinco tardes con Ernst Lubitsch
Del viernes 4 al domingo 13 de diciembre se llevará a cabo un ciclo denominado Cinco tardes con Ernst Lubitsch.
{RELLENO}
Viernes 4
A las 15 horas
El pecado de Cluny Brown
(Cluny Brown; Estados Unidos, 1946)
Dirección: Ernst Lubitsch.
(100′; DCP).
"""
fs, _ = correr()
assert ("2026-12-04", "15:00", "El pecado de Cluny Brown") in {(s.fecha, s.hora, s.title) for s in fs}, fs
print("✓ un ciclo de diciembre leído en noviembre sale en diciembre de este año")

# 9. El texto legible tiene que nombrar el evento.
assert not scraper._ctba_legible(None, "X")
assert not scraper._ctba_legible("Just a moment...", "Homenaje a John Huston")
assert scraper._ctba_legible(TEXTO_FINLANDIA, "Desde Finlandia con amor")
assert not scraper._ctba_legible(TEXTO_FINLANDIA, "Homenaje a John Huston")
print("✓ una página que no nombra el evento no cuenta como leída")

print("\nTodo OK")
