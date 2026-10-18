#!/usr/bin/env python3
"""
Test local del scraper del Museo Moderno (museomoderno.org/agenda), sin red:

    python3 test_moderno.py

El primer caso es la página real de "El cine es otra cosa 2026" (bajada el
18/10/2026). Los demás son eventos armados con el mismo HTML de Elementor y
JetEngine, para los formatos que el museo puede usar la próxima vez.
"""
from datetime import date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

import scraper
from scraper import _moderno_tarjetas, _parse_moderno_evento

HOY = date(2026, 10, 18)
FIN = HOY + timedelta(weeks=9)
URL = "https://museomoderno.org/agenda/prueba/"
ENTRADAS = "https://entradasba.buenosaires.gob.ar/evento/4bc7a911-cb06-4293-86ab-936310aa6e94"


def parse(html: str, hoy: date = HOY):
    return _parse_moderno_evento(BeautifulSoup(html, "html.parser"), URL, hoy,
                                 hoy + timedelta(weeks=9))


def evento(titulo: str, fechas: list[str], cuerpo: str) -> str:
    """Una página de evento con la forma de las del Moderno."""
    rep = "".join(f'<div class="jet-listing-dynamic-repeater__item"><div>{f} </div></div>'
                  for f in fechas)
    return (f'<h1 class="elementor-heading-title">{titulo}</h1>'
            f'<section><h6>Fechas recurrentes:</h6><div class="jet-listing-dynamic-repeater">'
            f'<div class="jet-listing-dynamic-repeater__items">{rep}</div></div></section>'
            f'<div class="elementor-widget-theme-post-content">{cuerpo}</div>')


# --- El ciclo real: El cine es otra cosa 2026 -------------------------------
real = (Path(__file__).parent / "tests" / "fixtures"
        / "moderno_el_cine_es_otra_cosa_2026.html").read_text(encoding="utf-8")
fs = parse(real)
assert [(s.fecha, s.hora, s.title, s.director, s.year, s.duration) for s in fs] == [
    ("2026-10-24", "19:00", "Los cruces", "Julián Galay", 2025, 83),
    ("2026-10-25", "18:00", "La orilla que se abisma", "Gustavo Fontán", 2008, 64),
], fs
assert all(s.cine == "Museo Moderno" and s.ciclo == "El cine es otra cosa" for s in fs)
assert all(s.ticket_url == ENTRADAS for s in fs), [s.ticket_url for s in fs]
print("✓ El cine es otra cosa: Los cruces (sáb 24, 19 h) y La orilla que se abisma (dom 25, 18 h)")
print("✓ director de 'Dirección, textos y diseño sonoro: Julián Galay', y año y duración de la ficha")
print("✓ la charla de Silvia Rivas del viernes 23 queda afuera: sus videoinstalaciones "
      "tienen año pero no duración ni director")

# La ventana manda: un día después del sábado sólo queda el domingo.
assert [s.title for s in parse(real, date(2026, 10, 25))] == ["La orilla que se abisma"]
print("✓ las fechas que ya pasaron no se publican")


# --- La agenda ---------------------------------------------------------------
def tarjeta(pid: str, tipo: str, slug: str, titulo: str) -> str:
    return (f'<div class="jet-listing-grid__item jet-listing-dynamic-post-{pid}" data-post-id="{pid}">'
            f'<a href="https://museomoderno.org/agenda/{slug}/"><img/></a>'
            f'<div class="jet-listing-dynamic-field__content" >{tipo}</div>'
            f'<h2 class="elementor-heading-title"><a href="https://museomoderno.org/agenda/{slug}/">'
            f'{titulo}</a></h2></div>')


agenda = ('<div class="jet-listing-grid__items" data-pages="3" data-page="1">'
          + tarjeta("62820", "Cine", "el-cine-es-otra-cosa-2026", "El cine es otra cosa 2026")
          + tarjeta("57018", "Actividades", "historias-compartidas-2", "Historias compartidas")
          + "</div>")
ts, paginas = _moderno_tarjetas(BeautifulSoup(agenda, "html.parser"))
assert paginas == 3
assert [(t["id"], t["tipo"], t["url"]) for t in ts] == [
    ("62820", "Cine", "https://museomoderno.org/agenda/el-cine-es-otra-cosa-2026/"),
    ("57018", "Actividades", "https://museomoderno.org/agenda/historias-compartidas-2/")], ts
print("✓ agenda: la etiqueta de cada tarjeta y cuántas páginas hay")

assert scraper._moderno_agenda_url(1, False) == "https://museomoderno.org/agenda/"
assert scraper._moderno_agenda_url(2, False) == (
    "https://museomoderno.org/agenda/?jsf=jet-engine:aplicarbusqueda&pagenum=2")
assert scraper._moderno_agenda_url(1, True) == (
    "https://museomoderno.org/agenda/?jsf=jet-engine:aplicarbusqueda&meta=tipo-de-evento:Cine")


# --- Una película que se repite, sin programa por día ------------------------
una = evento("Proyección: Zama", ["Jueves 5/11/26 19:00", "Viernes 6/11/26 20:30"], """
<p>El Moderno proyecta la película de Lucrecia Martel.</p>
<p><strong>–Zama</strong><br/>2017<br/>Ficción<br/>115 min</p>
<p><strong>Dirección:</strong> Lucrecia Martel</p>
<div class="elementor-button-wrapper"><a href="https://entradasba.buenosaires.gob.ar/evento/zama">
<span>¡Conseguí tus entradas!</span></a></div>""")
fs = parse(una)
assert [(s.fecha, s.hora, s.title, s.director, s.year) for s in fs] == [
    ("2026-11-05", "19:00", "Zama", "Lucrecia Martel", 2017),
    ("2026-11-06", "20:30", "Zama", "Lucrecia Martel", 2017)], fs
assert fs[0].ticket_url == "https://entradasba.buenosaires.gob.ar/evento/zama"
assert fs[0].ciclo == ""
print("✓ una película en dos fechas sin encabezados por día: la misma en las dos")
print("✓ 'Proyección: Zama' no es un ciclo")

# Sin guion adelante del título también es una ficha.
sin_guion = evento("Zama", ["Jueves 5/11/26 19:00"],
                   "<p><strong>Zama</strong><br/>2017<br/>115 min</p>")
fs = parse(sin_guion)
assert [(s.title, s.duration, s.ciclo) for s in fs] == [("Zama", 115, "")], fs
print("✓ ficha sin guion; y si el evento se llama como la película, no hay ciclo")

# Programa doble en una fecha: las dos películas en esa función.
doble = evento("Programa doble", ["Sábado 7/11/26 18:00"], """
<p>–La ciénaga<br/>2001<br/>103 min</p><p>Dirección: Lucrecia Martel</p>
<p>–La niña santa<br/>2004<br/>106 min</p><p>Dirección: Lucrecia Martel</p>""")
assert [(s.title, s.year) for s in parse(doble)] == [("La ciénaga", 2001), ("La niña santa", 2004)]
print("✓ programa doble en una sola fecha: una fila por película")

# Dos películas y dos fechas sin decir cuál va cuándo: mejor nada que adivinar.
ambiguo = evento("Ciclo Martel", ["Sábado 7/11/26 18:00", "Domingo 8/11/26 18:00"], """
<p>–La ciénaga<br/>2001<br/>103 min</p>
<p>–La niña santa<br/>2004<br/>106 min</p>""")
assert parse(ambiguo) == []
print("✓ dos películas en dos fechas sin programa por día: no se publica")


# --- Programa por día, con la hora en el texto ------------------------------
# Un evento de rango ("Fechas: De 5/11 a 6/11") no tiene el campo con la
# hora: salen las fechas de los encabezados y la hora de abajo.
rango = """<h1>Ciclo de noviembre</h1>
<section><span>Fechas:</span> De 5/11 a 6/11</section>
<div class="elementor-widget-theme-post-content">
<h4>Jueves 5 de noviembre</h4><p><strong>20.30 h</strong></p>
<p><b>–Zama</b><br/>2017<br/>115 min</p>
<h4>Viernes 6 de noviembre</h4><p><strong>19 h</strong></p>
<p><b>–Rojo</b><br/>2018<br/>109 min<br/>Dirección: Benjamín Naishtat</p>
<h4>Sobre los realizadores</h4>
<p>–El otro<br/>2007<br/>83 min</p>
</div>"""
fs = parse(rango)
assert [(s.fecha, s.hora, s.title) for s in fs] == [
    ("2026-11-05", "20:30", "Zama"), ("2026-11-06", "19:00", "Rojo")], fs
assert fs[1].director == "Benjamín Naishtat"
print("✓ sin el campo de fechas: la fecha del encabezado y la hora de abajo ('20.30 h')")
print("✓ un título que no es un día cierra el último día: El otro no se cuela el viernes")

# Un día del texto que no está en el campo de fechas no se publica, y un día
# del campo que no está en el texto tampoco.
cruzado = evento("Ciclo", ["Sábado 7/11/26 18:00"], """
<h4>Domingo 8 de noviembre de 2026</h4><p>18 h</p><p>–Rojo<br/>2018<br/>109 min</p>""")
assert parse(cruzado) == []
print("✓ si el campo de fechas y el texto no coinciden, no se adivina")

print("\nTodo OK")
