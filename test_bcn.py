#!/usr/bin/env python3
"""
Test local del scraper de la Biblioteca del Congreso, sin red.

    python3 test_bcn.py

El modo de falla que arregla (stories del 8/10/2026): el 21.° Festival de Cine
Inusual salió como dos filas, "21.° Festival de Cine Inusual de Buenos Aires"
con director "La BCN será nuevamente sede del Festival" y "Proyección de
cortometrajes" con director "Dentro del marco del marco del 21.° Festival…".
Tres cosas juntas:
  - el cronograma del festival venía con otro formato ("Cronograma:" con dos
    puntos, sin la etiqueta "Cortometraje:" antes de cada título);
  - las cards de cada película apuntan a un cascarón que redirige por JS a la
    página del festival, así que nunca se veía el cronograma;
  - la bajada de la card ("Dentro del marco…") se tomaba como director.
"""
from datetime import date
from unittest import mock

from bs4 import BeautifulSoup

import scraper
from scraper import _bcn_cronograma, _bcn_fetch, _bcn_parse_corta

HOY = date(2026, 10, 8)

# Como lo publicó la BCN para el festival (recortado).
FESTIVAL = """
<html><body>
<script>window.location = "https://consulta.bcn.gob.ar/web/catalogo?q=" + q;</script>
<h1>21.° Festival de Cine Inusual de Buenos Aires</h1>
<p>La BCN será nuevamente sede del Festival</p>
<p>Del 08 al 15 de octubre, 18.30 h</p>
<div class="contenido">
<p><span>Cronograma:</span></p>
<p><b>Proyección de cortometrajes:</b></p>
<div><i>calendar_clock</i><span><b><span>Jueves 8 de octubre - </span><span>18.30 h</span></b></span></div>
<div><i>place</i><span>Auditorio Leonardo Favio (Alsina 1835, CABA)</span></div>
<a href="https://www.eventbrite.com.ar/e/proyeccion-de-cortometrajes-1">Entradas</a>
<div><span><b><i>7 minutos</i></b></span></div>
<div><span>Dirección: Pablo Panaro</span></div>
<div><span>Año: 2026</span></div>
<div><span>Duración: 08´ 35’’<br/>Pablo, un hombre de setenta años marcado por la depresión.</span></div>
<div><span><b><i>El eco</i></b></span></div>
<div><span>Dirección: Leandro Panei</span></div>
<div><span>Año: 2026</span></div>
<div><span>Duración: 19´ 09’’<br/>Cuatro bohemios borrachos.</span></div>
<div><i>calendar_clock</i><span>Martes 13 de octubre -</span></div>
<div><span>18.30 h</span></div>
<a href="https://www.eventbrite.com.ar/e/cielomoto">Entradas</a>
<div><span><b>Cielomoto</b></span></div>
<div><span>Dirección: Manuel López Márquez</span></div>
<div><span>Año: 2026</span></div>
<div><span>Duración: 65´</span></div>
<div><i>calendar_clock</i><span>Jueves 15 de octubre - 18.30 h</span></div>
<a href="https://www.eventbrite.com.ar/e/la-reina">Entradas</a>
<div><span><b>La Reina, el Buda y Buñuel (México)</b></span></div>
<div><span>Dirección: Alexander Katzowicz</span></div>
<div><span>Año: 2026</span></div>
<div><span>Duración: 81´</span></div>
</div>
<h3>Contenido relacionado</h3>
<p>Ciclo de cine: Clásicos de cine noir norteamericano</p>
</body></html>
"""

crono = _bcn_cronograma(BeautifulSoup(FESTIVAL, "html.parser"),
                        "21.° Festival", "https://bcn.gob.ar/cine/festival", HOY)
filas = [(s.fecha, s.hora, s.title, s.director, s.year, s.duration)
         for s in crono]
assert filas == [
    ("2026-10-08", "18:30", "7 minutos", "Pablo Panaro", 2026, 8),
    ("2026-10-08", "18:30", "El eco", "Leandro Panei", 2026, 19),
    ("2026-10-13", "18:30", "Cielomoto", "Manuel López Márquez", 2026, 65),
    ("2026-10-15", "18:30", "La Reina, el Buda y Buñuel", "Alexander Katzowicz", 2026, 81),
], filas
assert [s.ticket_url.rsplit("/", 1)[1] for s in crono] == [
    "proyeccion-de-cortometrajes-1", "proyeccion-de-cortometrajes-1",
    "cielomoto", "la-reina"], [s.ticket_url for s in crono]
# "(México)" es el país, no el título original.
assert crono[3].original_title == "" and crono[3].country == "México", crono[3]
print("✓ cronograma nuevo: una fila por película, con ficha y entrada por fecha")

# El formato de agosto (con la etiqueta "Cortometraje:") sigue andando.
VIEJO = """
<html><body><div>
<p>Cronograma</p>
<p>calendar_clock</p><p>Martes 18 de agosto -</p><p>18.30 h</p>
<p>Cortometraje:</p><p>The Fortunate</p>
<p>Dirección: Habtamu Gebrehiwot,</p><p>Año: 2026</p><p>Duración: 15´</p>
<p>Largometraje: Collateral</p>
<p>Dirección: Michael Mann</p><p>Año: 2004</p><p>Duración: 120´</p>
</div></body></html>
"""
viejo = _bcn_cronograma(BeautifulSoup(VIEJO, "html.parser"), "c", "u",
                        date(2026, 8, 1))
assert [(s.title, s.director, s.year) for s in viejo] == [
    ("The Fortunate", "Habtamu Gebrehiwot", 2026),
    ("Collateral", "Michael Mann", 2004),
], [(s.title, s.director, s.year) for s in viejo]
print("✓ cronograma viejo (Cortometraje: / Largometraje:)")

# La bajada de la card: sin ficha no hay director; con "Proyección película
# de" el director es el nombre.
assert _bcn_parse_corta("La BCN será nuevamente sede del Festival.") == {}
assert _bcn_parse_corta(
    "Dentro del marco del marco del 21.° Festival de Cine Inusual de Buenos Aires.") == {}
assert _bcn_parse_corta("Proyección película de Ridley Scott. 1982, 117’.") == {
    "director": "Ridley Scott", "year": 1982, "duration": 117}
assert _bcn_parse_corta("Película de César González. 2025, 68’.")["director"] == "César González"
assert _bcn_parse_corta("Steven Spielberg, 1987, 152’")["director"] == "Steven Spielberg"
print("✓ bajada corta: sin frases institucionales ni 'Proyección película de'")

# El cascarón de cada película redirige al festival; una página con contenido
# (aunque tenga el window.location del buscador) no.
CASCARON = """<html><head><title>BCN - Cielomoto</title></head><body>
<script type="text/javascript">
    window.location.href = 'https://bcn.gob.ar/cine/21-festival';
</script></body></html>"""
paginas = {
    "https://bcn.gob.ar/21-festival/cielomoto": CASCARON,
    "https://bcn.gob.ar/cine/21-festival": FESTIVAL,
}
with mock.patch.object(scraper, "fetch_html",
                       lambda u: BeautifulSoup(paginas[u], "html.parser")):
    assert _bcn_fetch("https://bcn.gob.ar/21-festival/cielomoto").find("h1")
    assert _bcn_fetch("https://bcn.gob.ar/cine/21-festival").find("h1")
print("✓ redirect por JS: el cascarón lleva al festival, el buscador no")
