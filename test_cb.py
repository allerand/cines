#!/usr/bin/env python3
"""
Test local del parseo de las fichas de la Casa Nacional del Bicentenario
(_cb_parse_detail), sin red:

    python3 test_cb.py

El modo de falla que arregla: el parser buscaba UNA película en el renglón de
cada fecha. OFFNI CINE FEST (octubre de 2026) pone la fecha como encabezado y
abajo de dos a siete películas, cada una en renglones "Director: / Año: /
País: / Duración:", a veces en el párrafo siguiente. De cada día salía como
mucho la primera, con el rótulo pegado ("— DÍA UFO DIARY OF AN ABANDONED
ALIEN"), y se perdían las que venían en otro párrafo. "Noche adentro" está
escrita en prosa y entraba sólo por el fallback que publicaba el nombre de la
actividad, que en un ciclo de varias fechas es una función inventada.

Los fixtures son las fichas publicadas el 25/10/2026, recortadas al título,
el cuerpo y el bloque Cuándo/Horario. Los formatos viejos son los que
documenta el código (los ciclos hasta agosto de 2026).
"""
from pathlib import Path

from bs4 import BeautifulSoup

from scraper import _cb_parse_detail

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
URL_OFFNI = "https://casadelbicentenario.cultura.gob.ar/actividad/kino-cnb-offni-cine-fest-1/"
URL_NOCHE = "https://casadelbicentenario.cultura.gob.ar/actividad/cine-noche-adentro/"


def parsear(html: str, url: str = "u"):
    return _cb_parse_detail(BeautifulSoup(html, "html.parser"), url)


def fila(s):
    return (s.fecha, s.hora, s.title, s.director, s.country, s.year, s.duration)


# --- OFFNI CINE FEST: la fecha de encabezado y varias películas abajo --------
offni = parsear((FIXTURES / "cb_offni_cine_fest_2026.html").read_text(encoding="utf-8"),
                URL_OFFNI)
por_dia = {}
for s in offni:
    por_dia.setdefault((s.fecha, s.hora), []).append(s.title)
assert {k: len(v) for k, v in por_dia.items()} == {
    ("2026-10-09", "19:00"): 2, ("2026-10-10", "18:00"): 5, ("2026-10-11", "18:00"): 4,
    ("2026-10-16", "19:00"): 3, ("2026-10-17", "18:00"): 4, ("2026-10-18", "18:00"): 5,
    ("2026-10-23", "19:00"): 3, ("2026-10-24", "18:00"): 1, ("2026-10-25", "18:00"): 2,
    ("2026-10-30", "19:00"): 3, ("2026-10-31", "18:00"): 3, ("2026-11-01", "18:00"): 7,
}, por_dia
assert {s.ciclo for s in offni} == {"OFFNI CINE FEST"}
assert {s.ticket_url for s in offni} == {URL_OFFNI}
filas = {s.title: fila(s) for s in offni}
assert filas["LA COSA EN LA NIEBLA"] == (
    "2026-10-09", "19:00", "LA COSA EN LA NIEBLA", "Chedey Reyes", "España", 2025, 83)
# El rótulo del día no se pega al título.
assert por_dia[("2026-10-10", "18:00")][0] == "DIARY OF AN ABANDONED ALIEN"
# ROOM 404 y PARAPETO van en otro párrafo, debajo del mismo encabezado.
assert por_dia[("2026-10-11", "18:00")] == ["FROM MOSCOW", "MARDAZMA", "ROOM 404", "PARAPETO"]
assert filas["PARAPETO"][-1] == 124                      # "2 h 4 min 55 s"
assert filas["FROM MOSCOW"][3] == "Tatiana Fedyunina"    # "Directora:"
assert filas["HOME MOVIE LEGEND TRIP: THE BEAST OF BRAY ROAD"][3] == "Dean Bertram y Samantha Krause"
assert filas["THE INCIDENTS AT PAWGUR, 1830"][5] == 2026  # el 1830 es del título
# El Día Esotérico: la ficha en un renglón con puntos, y la película sorpresa
# (sin director ni año) no es una función que se pueda publicar.
assert filas["LAS ZAPATILLAS"] == (
    "2026-10-24", "18:00", "LAS ZAPATILLAS", "Jonathan Rodríguez", "Argentina", 2026, 30)
assert not any("OCULTA" in t or "sorpresa" in t for t in filas)
print(f"✓ offni: {len(offni)} películas en sus 12 días, con director, país, año y duración")

# --- Noche adentro: una película contada en prosa -----------------------------
noche = parsear((FIXTURES / "cb_noche_adentro_2026.html").read_text(encoding="utf-8"),
                URL_NOCHE)
assert [fila(s) for s in noche] == [
    ("2026-11-07", "18:30", "Noche adentro", "Francisco Olivero", "", None, None)], noche
assert noche[0].ciclo == "" and noche[0].ticket_url == URL_NOCHE
print("✓ noche adentro: la película de la prosa, a las 18.30 que dice el texto")

# --- Formatos viejos -----------------------------------------------------------
CUANDO_JUNIO = "<h4>Cuándo</h4><div>A partir del 7 Jun. 2026 Hasta el 28 Jun. 2026</div>"
viejo = parsear(f"""<h1>CINE | Miradas de Japón</h1><div class="article">
<p><strong>Domingo 7.</strong> 19HS Muña Muña (2025) Dur. 67 min. Guion y dirección: Julia Pesce</p>
<p>Domingo 14 de junio, 19HS Cinéfilos (2024) Dir. Arnaud Desplechin. 88 min</p>
<p>Domingo 21/6. 19HS</p>
<p>Escenas en el mar (1991, 101m. Dir. Takeshi Kitano) *(Ano Natsu, Ichiban Shizukana Umi)</p>
<p>Domingo 28. 19HS SUSPENDIDA Ataduras (1998) Dir. Kichitaro Negishi. 124 min</p>
</div>{CUANDO_JUNIO}<h4>Horario</h4><div>Domingo 19:00 a 21:00</div>""")
assert [(s.fecha, s.hora, s.title, s.director, s.year, s.duration) for s in viejo] == [
    ("2026-06-07", "19:00", "Muña Muña", "Julia Pesce", 2025, 67),
    ("2026-06-14", "19:00", "Cinéfilos", "Arnaud Desplechin", 2024, 88),
    ("2026-06-21", "19:00", "Escenas en el mar", "Takeshi Kitano", 1991, 101),
], viejo
assert viejo[2].original_title == "Ano Natsu, Ichiban Shizukana Umi"
assert {s.ciclo for s in viejo} == {"Miradas de Japón"}
print("✓ formatos viejos: la película en el renglón de la fecha o abajo; la suspendida no")

# --- Lo que no es una función -------------------------------------------------
# Una fecha en la prosa de la presentación, sin verbo de proyección.
assert parsear(f"""<h1>CINE | Ciclo</h1><div class="article">
<p>El sábado 13 de junio a las 19, la Casa recibe al Festival <em>Cortos del Sur</em>.</p>
<p>Jueves 18 de junio. 19HS Los filmes que componen este programa recorren la ciudad.</p>
</div>{CUANDO_JUNIO}""") == []
# Un ciclo de varias fechas sin películas legibles no publica su nombre.
assert parsear(f"""<h1>KINO CNB | Algo nuevo</h1><div class="article">
<p>Todos los domingos de junio, una selección de cortos.</p></div>{CUANDO_JUNIO}""") == []
# Una actividad de un solo día sí: es la película misma.
uno = parsear("""<h1>CINE | La película</h1><div class="article">
<p>Una función especial.</p></div><h4>Cuándo</h4><div>20 Jun. 2026</div>
<h4>Horario</h4><div>Abierto de 18:30 a 20:00</div>""")
assert [(s.fecha, s.hora, s.title, s.ciclo) for s in uno] == [("2026-06-20", "18:30", "La película", "")]
print("✓ sin función: la prosa con fecha y el ciclo sin programa no inventan filas")

print("\nTodo OK")
