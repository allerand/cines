#!/usr/bin/env python3
"""
Test local del scraper de Cine para Lectores (Casa de la Lectura y la
Escritura), sin red:

    python3 test_lectores.py

Los posts son los reales de agendacultural15.com de 2026, recortados.
"""
from datetime import date

import scraper
from scraper import (_lectores_ciclo, _lectores_ficha, _lectores_funciones, _lectores_posts,
                     LECTORES_CINE)


def post(fecha, cuerpo, titulo="Cine para Lectores en Casa de la Lectura y la Escritura",
         link="https://agendacultural15.com/cine-para-lectores-en-casa-de-la-lectura-y-la-escritura-2/"):
    return {"date": fecha, "link": link, "title": {"rendered": titulo},
            "content": {"rendered": cuerpo}}


NOVIEMBRE = post("2026-11-02T15:15:10", """
<p>El ciclo de Cine para Lectores en Casa de la Lectura y la Escritura, Lavalleja 924, en el barrio de Villa Crespo, presenta un ciclo dedicado al cine argentino reciente.</p>
<p>La Red de Bibliotecas presenta el último ciclo del año de <strong>Cine para Lectores: Muestra de cine argentino reciente</strong>. Desde el 5 de noviembre hasta el 10 de diciembre, los films se proyectarán todos los jueves a las 18 horas.</p>
<p><strong>Programación</strong></p>
<p><strong>Noviembre</strong></p>
<p><strong>Jueves 5 a las 18hs</strong>: “Los ríos” (Argentina, 2024, 52´), de Gustavo Fontán.<br>
<strong>Jueves 19 a las 18hs</strong>: “Mixtape La Pampa”  (Argentina-Chile, 2023, 104´), de Andrés Di Tella. </p>
<p><strong>Diciembre</strong></p>
<p><strong>Jueves 3 a las 18hs</strong>: “La gruta continua” (Argentina, 2023, 85´), de Julián D’Angiolillo. <br>
<strong>Jueves 10 a las 18hs</strong>: “Ciudad oculta” (Argentina, 2024, 95´), de Francisco Bouzas. </p>
<p>Entrada gratuita.</p>
""")

# Agosto: sin renglón de mes, y la última función ya es de septiembre.
AGOSTO = post("2026-08-03T12:49:36", """
<p>La Red de Bibliotecas presenta un nuevo ciclo de Cine para Lectores: Retrospectiva Edgardo Cozarinsky, una selección de películas del gran cineasta argentino. Desde el 6 de agosto hasta el 3 de septiembre en Casa de la Lectura y la Escritura.</p>
<p>Jueves 6 a las 18hs: “La guerra de un solo hombre” (La guerre d’un seul homme, Francia, 1982, 105´), de Edgardo Cozarinsky.</p>
<p>Jueves 13 a las 18hs: “Ciudadano Langlois” (Citizen Langlois, 1995, 69´), de Edgardo Cozarinsky.</p>
<p>Jueves 3 a las 18hs: “Carta a un padre” (2013, 65´), de Edgardo Cozarinsky.</p>
""", titulo="Cine para Lectores en Casa de la Lectura")

# Mayo: dos ciclos en el mismo post; el primero no dice "Cine para Lectores:".
MAYO = post("2026-04-29T17:54:29", """
<p>En el marco de la Feria Internacional del Libro, donde Perú es el país invitado de honor, Cine para Lectores presenta una selección de películas de la cinematografía del país andino.</p>
<p>Jueves 7 a las 18hs: “Kinra” (Perú, 2025, 157´), de Marco Panatonic.</p>
<p>La Red de Bibliotecas presenta un nuevo ciclo de Cine para Lectores: Encuentro con el cine chileno, una selección de películas de la cinematografía chilena contemporánea.</p>
<p>Jueves 18 a las 18hs: “Una sombra oscilante” (Chile, Argentina, España, Francia-2024, 77´), de Celeste Rojas Mugica.</p>
<p>Jueves 16 a las 18hs: “La casa lobo” (2018, Chile, 75´), de Joaquín Cociña y Cristóbal León.</p>
""", titulo="Cine para Lectores en Casa de la Lectura")

# --- El ciclo -----------------------------------------------------------------
assert _lectores_ciclo("Cine para Lectores: Muestra de cine argentino reciente. Desde el 5") == \
    "Cine para Lectores - Cine argentino reciente"
assert _lectores_ciclo("un nuevo ciclo de Cine para Lectores: Chabrol x 3, una selección") == \
    "Cine para Lectores - Chabrol x 3"
assert _lectores_ciclo("El ciclo de Cine para Lectores en Casa de la Lectura") == "Cine para Lectores"
print("✓ ciclo: 'Cine para Lectores - <lo que sigue a los dos puntos>', sin 'Muestra de'")

# --- La ficha -----------------------------------------------------------------
assert _lectores_ficha("Argentina-Chile, 2023, 104´") == {
    "original_title": "", "country": "Argentina, Chile", "year": 2023, "duration": 104}
assert _lectores_ficha("Le beau Serge, Francia, 1959, 99´") == {
    "original_title": "Le beau Serge", "country": "Francia", "year": 1959, "duration": 99}
assert _lectores_ficha("Citizen Langlois, 1995, 69´")["original_title"] == "Citizen Langlois"
assert _lectores_ficha("2018, Chile, 75´")["country"] == "Chile"
assert _lectores_ficha("Chile, Argentina, España, Francia-2024, 77´") == {
    "original_title": "", "country": "Chile, Argentina, España, Francia", "year": 2024, "duration": 77}
print("✓ ficha: título original, países, año y duración en cualquier orden")

# --- Noviembre: con renglones de mes ------------------------------------------
fs = _lectores_funciones(NOVIEMBRE)
assert [(s.fecha, s.hora, s.title) for s in fs] == [
    ("2026-11-05", "18:00", "Los ríos"),
    ("2026-11-19", "18:00", "Mixtape La Pampa"),
    ("2026-12-03", "18:00", "La gruta continua"),
    ("2026-12-10", "18:00", "Ciudad oculta"),
], fs
mixtape = fs[1]
assert mixtape.cine == LECTORES_CINE
assert mixtape.ciclo == "Cine para Lectores - Cine argentino reciente"
assert (mixtape.director, mixtape.country, mixtape.year, mixtape.duration) == \
    ("Andrés Di Tella", "Argentina, Chile", 2023, 104)
assert mixtape.ticket_url.startswith("https://agendacultural15.com/")
print("✓ noviembre: cuatro funciones, la de Mixtape La Pampa con su ficha y su ciclo")

# --- Agosto: el mes sale del día de la semana ---------------------------------
fs = _lectores_funciones(AGOSTO)
assert [s.fecha for s in fs] == ["2026-08-06", "2026-08-13", "2026-09-03"], fs
assert fs[0].ciclo == "Cine para Lectores - Retrospectiva Edgardo Cozarinsky"
assert fs[0].original_title == "La guerre d’un seul homme"
print("✓ agosto: sin renglón de mes, 'Jueves 3' es el 3 de septiembre")

# --- Mayo: dos ciclos en un post -------------------------------------------------
fs = _lectores_funciones(MAYO)
assert [(s.fecha, s.title, s.ciclo) for s in fs] == [
    ("2026-05-07", "Kinra", "Cine para Lectores"),
    ("2026-06-18", "Una sombra oscilante", "Cine para Lectores - Encuentro con el cine chileno"),
    ("2026-07-16", "La casa lobo", "Cine para Lectores - Encuentro con el cine chileno"),
], fs
assert fs[2].director == "Joaquín Cociña y Cristóbal León"
print("✓ mayo: cada película con el ciclo que la presenta; nunca una fecha para atrás")

# --- Los posts ------------------------------------------------------------------
otros = {"date": "2026-09-30T13:53:22", "title": {"rendered": "Festival Internacional de Literatura (FILBA)"},
         "content": {"rendered": "<p>lectores</p>"}}
assert [p["date"] for p in _lectores_posts([AGOSTO, otros, NOVIEMBRE])] == \
    ["2026-11-02T15:15:10", "2026-08-03T12:49:36"]
assert _lectores_posts({"code": "rest_no_route"}) == []
print("✓ posts: sólo los de Cine para Lectores, del más nuevo al más viejo")

# --- scrape_lectores, con la API simulada ----------------------------------------
import json
real_fetch = scraper.fetch_bytes
real_date = scraper.date


class Hoy(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 19)


try:
    scraper.date = Hoy
    scraper.fetch_bytes = lambda url, *a, **k: json.dumps([NOVIEMBRE, otros]).encode()
    scraper.FUENTES_CAIDAS.clear()
    fs = scraper.scrape_lectores(9)
    assert [s.fecha for s in fs] == ["2026-11-19", "2026-12-03", "2026-12-10"], fs
    assert not scraper.FUENTES_CAIDAS

    scraper.fetch_bytes = lambda url, *a, **k: json.dumps([otros]).encode()
    assert scraper.scrape_lectores(9) == []
    assert LECTORES_CINE in scraper.FUENTES_CAIDAS

    def caida(url, *a, **k):
        raise TimeoutError()
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = caida
    assert scraper.scrape_lectores(9) == []
    assert "no contestó" in scraper.FUENTES_CAIDAS[LECTORES_CINE]
finally:
    scraper.fetch_bytes = real_fetch
    scraper.date = real_date
    scraper.FUENTES_CAIDAS.clear()
print("✓ scrape_lectores: desde hoy (la de esta tarde incluida); sin posts o sin red, fuente caída")
print("\nOK")
