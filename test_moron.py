#!/usr/bin/env python3
"""
Test local del scraper del Espacio INCAA Morón (ellaferrere.com.ar), sin red:

    python3 test_moron.py

Los párrafos son los reales de la nota de noviembre de 2026, recortados.
"""
from datetime import date

import scraper
from scraper import _moron_fecha, _moron_ficha, _moron_funciones


def nota(cuerpo, editada="2026-11-06T14:41:06+00:00"):
    return (f'<html><head><meta property="article:modified_time" content="{editada}"></head><body>'
            f'<div class="entry-content">{cuerpo}</div></body></html>')


NOVIEMBRE = nota("""
<h2><em>Nuestro cine, nuestra identidad</em></h2>
<h1>Noviembre</h1>
<h2>Estrenos</h2>
<p><strong><mark><strong><mark>Miércoles 4, 20hs | Miércoles 11, 20hs</mark></strong></mark></strong><br/>
<strong>El club de pesca,</strong> de Gastón Horacio Revol Molina | Drama – Trhiller | 94MIN | R-13 |</p>
<p><strong>Con</strong> Adrián Azaceta, Paula Brasca, Iván Espeche</p>
<p><em><strong>Rodrigo y Valentina</strong> sufren una crisis matrimonial.</em></p>
<p><strong><mark><strong><mark>Viernes 13, 20hs | <strong>Miércoles 18, 20hs | Viernes 20, 20hs | Miércoles 25, 20h</strong>s</mark></strong></mark></strong><br/>
<strong>La casa</strong>, de Gustavo Triviño | Argentina | 2026 | Drama Thriller | Duración 108 minutos | R-13</p>
<h2>Mirada documental</h2>
<p><strong><mark><strong><mark>Jueves 19, 20hs</mark></strong></mark></strong><br/>
<strong>Militante</strong>, de Federico Sosa | Argentina | 2025 | Documental | Duración 61 minutos | G | Con Pablo Ayala.</p>
<h2>Pequeños grandes mundos</h2>
<p><em>Humor, aventura y fantasía para descubrir, imaginar y crecer.</em></p>
<p><strong><mark><strong><mark>Domingo 22, 16hs</mark></strong></mark></strong><br/>
<strong>Natacha, la película</strong>, de Eduardo Pinto, Fernanda Ribeiz | Argentina | 2017 | Comedia infantil | Duración 75 minutos | Recomendada para chicos desde 6-7 años en adelante</p>
<h2>Cierre del 4to Festival de Cine Indígena BAIn 2026</h2>
<p><strong><mark><strong><mark>Domingo 29, 18hs</mark></strong></mark></strong><br/>
<strong>Retazos de memoria,</strong> de Juan Pablo Tobal | Documental | 2026 | 76 MIN </p>
""")

# --- La ficha -----------------------------------------------------------------
assert _moron_ficha(" de Gastón Horacio Revol Molina | Drama – Trhiller | 94MIN | R-13 |") == {
    "director": "Gastón Horacio Revol Molina", "country": "", "year": None, "duration": 94}
assert _moron_ficha(", de Gustavo Triviño | Argentina | 2026 | Drama Thriller | Duración 108 minutos | R-13") == {
    "director": "Gustavo Triviño", "country": "Argentina", "year": 2026, "duration": 108}
assert _moron_ficha(" de Juan Pablo Tobal | Documental | 2026 | 76 MIN ") == {
    "director": "Juan Pablo Tobal", "country": "", "year": 2026, "duration": 76}
assert _moron_ficha(", de Ana Pérez | Argentina – Uruguay | 2024 | Drama | 90MIN")["country"] == "Argentina, Uruguay"
assert _moron_ficha(" | Drama | 80MIN")["director"] == ""
print("✓ ficha: director, año, duración ('94MIN', '108 minutos') y país sólo si es un país")

# --- La fecha -----------------------------------------------------------------
ref = date(2026, 11, 6)
assert _moron_fecha(11, 18, 2, ref) == date(2026, 11, 18)        # miércoles
assert _moron_fecha(11, 18, 3, ref) is None                      # no es jueves
assert _moron_fecha(1, 6, 2, date(2026, 12, 28)) == date(2027, 1, 6)   # enero, editada en diciembre
assert _moron_fecha(2, 30, 0, ref) is None
print("✓ fecha: el año es el que hace coincidir el día de la semana; si no coincide, no sale")

# --- Las funciones --------------------------------------------------------------
fs = _moron_funciones(NOVIEMBRE)
assert [(s.title, s.fecha, s.hora, s.ciclo) for s in fs] == [
    ("El club de pesca", "2026-11-04", "20:00", ""),
    ("El club de pesca", "2026-11-11", "20:00", ""),
    ("La casa", "2026-11-13", "20:00", ""),
    ("La casa", "2026-11-18", "20:00", ""),
    ("La casa", "2026-11-20", "20:00", ""),
    ("La casa", "2026-11-25", "20:00", ""),
    ("Militante", "2026-11-19", "20:00", "Mirada documental"),
    ("Natacha, la película", "2026-11-22", "16:00", "Pequeños grandes mundos"),
    ("Retazos de memoria", "2026-11-29", "18:00", "Cierre del 4to Festival de Cine Indígena BAIn 2026")], fs
casa = fs[2]
assert (casa.cine, casa.director, casa.country, casa.year, casa.duration) == (
    "Espacio INCAA Morón", "Gustavo Triviño", "Argentina", 2026, 108)
assert fs[7].director == "Eduardo Pinto, Fernanda Ribeiz"
assert casa.ticket_url == scraper.MORON_URL
print("✓ una función por cada día resaltado, aunque la hora venga partida ('20h' + 's')")
print("✓ 'Estrenos' no es un ciclo; las demás secciones sí; la coma del título compuesto se queda")

# El reparto, la sinopsis y la bajada de la sección no son funciones.
assert not any(s.title.startswith(("Con", "Rodrigo", "Humor")) for s in fs)
# Un mes viejo que quedó en la nota: los días no coinciden y no sale nada.
vieja = nota("<h1>Octubre</h1><h2>Estrenos</h2><p><strong><mark>Miércoles 4, 20hs</mark></strong><br/>"
             "<strong>Algo</strong>, de Alguien | 90MIN</p>")
assert _moron_funciones(vieja) == []
assert _moron_funciones(nota("<h2>Estrenos</h2><p><strong><mark>Miércoles 4, 20hs</mark></strong><br/>"
                             "<strong>Sin mes</strong>, de Alguien</p>")) == []
assert _moron_funciones("<html><body><p>Sitio en mantenimiento</p></body></html>") == []
print("✓ sin mes, con los días corridos o sin nota no inventa funciones")


# --- scrape_moron -------------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 18)


_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: NOVIEMBRE.encode("utf-8")
    r = scraper.scrape_moron()
    assert [(s.title, s.fecha) for s in r] == [
        ("La casa", "2026-11-18"), ("La casa", "2026-11-20"), ("La casa", "2026-11-25"),
        ("Militante", "2026-11-19"), ("Natacha, la película", "2026-11-22"),
        ("Retazos de memoria", "2026-11-29")], r
    assert not scraper.FUENTES_CAIDAS
    print("✓ scrape_moron: sólo lo que viene")

    scraper.fetch_bytes = lambda url, *a, **k: b"<html><body>Sitio en mantenimiento</body></html>"
    assert scraper.scrape_moron() == [] and "no trae ninguna" in scraper.FUENTES_CAIDAS["Espacio INCAA Morón"]

    def _caida(url, *a, **k):
        raise TimeoutError("timed out")
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = _caida
    assert scraper.scrape_moron() == [] and "no contestó" in scraper.FUENTES_CAIDAS["Espacio INCAA Morón"]
    print("✓ si la nota cambia de forma o el sitio no contesta, avisa a la auditoría")
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
