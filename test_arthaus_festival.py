#!/usr/bin/env python3
"""
Test local del parseo de arthaus.ar/cine/ (_parse_arthaus_seccion), sin red.

    python3 test_arthaus_festival.py

El modo de falla que arregla: las jornadas de festival ("día 3", "día 4") no
traen una fecha por película — la fecha está una sola vez en la cabecera del
día y cada función arranca con su propia línea de hora. El parser viejo leía
todo como fichas sueltas, así que el bloque de cada película se estiraba hasta
el próximo "Dir." y se comía la cabecera del día siguiente. Resultado del
13/9: Ramón Vázquez, que daba el SÁBADO 12 a las 20.45, salió publicada el
DOMINGO 13 a las 18 H —el horario de la charla de apertura del domingo— y las
otras tres películas del fin de semana no salieron, porque su bloque no tenía
ninguna línea de fecha adentro y se descartaban en silencio.

El HTML es el de la página real: la web parte el <strong> de la hora del <em>
del título, y el "Dir. NOMBRE" del "(duración: NN’)", así que el innerText
devuelve cada uno en su propia línea.
"""
from datetime import date, timedelta

from bs4 import BeautifulSoup

from scraper import _inner_text, _parse_arthaus_seccion


def parsear(html: str, hoy: str, ciclo: str = "") -> list[dict]:
    soup = BeautifulSoup(f"<section>{html}</section>", "html.parser")
    lineas = [l for l in _inner_text(soup).split("\n") if l]
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    today = date.fromisoformat(hoy)
    scr = _parse_arthaus_seccion(lineas, hrefs, ciclo, today,
                                 today + timedelta(weeks=6))
    return [{"fecha": s.fecha, "hora": s.hora, "title": s.title,
             "director": s.director, "duration": s.duration,
             "ticket_url": s.ticket_url, "ciclo": s.ciclo} for s in scr]


# --- La sección del festival: dos jornadas, una al lado de la otra. ----------
DIA_3 = "https://www.alternativateatral.com/obra102780-dia-3"
DIA_4 = "https://www.alternativateatral.com/obra102781-dia-4"

FESTIVAL = f"""
<div class="elementor-column">
  <h3>día 3</h3>
  <p><strong>Sábado 12 de septiembre, 18 H Conversación (entrada libre y gratuita)</strong>
     ¿Qué mira un programador? Una conversación sobre criterios de selección.<br/>
     <strong>Participan: Violeta Bava &amp; Diego Trerotola.</strong></p>
  <p>+<br/>
     <strong>19.15 H – <em>LOS CRUCES</em></strong><br/>
     Dir. Julián Galay <em>(duración: 71’)</em><br/>
     +<br/>
     <strong>20.45 H – <em>RAMÓN VÁZQUEZ</em></strong><br/>
     Dir. Gustavo Fontán <em>(duración: 68’)</em></p>
  <a href="{DIA_3}">ENTRADAS</a>
</div>
<div class="elementor-column">
  <h3>día 4</h3>
  <p><strong>Domingo 13 de septiembre, 18 H Conversación (entrada libre y gratuita)</strong>
     ¿Cómo encuentra una película su festival? Una conversación sobre
     programación y circulación.<br/>
     <strong>Participan: Louise Martin Papasian &amp; Mauro Lukasievicz.</strong></p>
  <p>+<br/>
     <strong>19.30 H – <em>Cortos II</em></strong><br/>
     <em>(Lengua muerta + Ezkutuko Materialak)</em><br/>
     +<br/>
     <strong>20.30 H – <em>SABES DE MIM AGORA ESQUEÇA</em></strong><br/>
     Dir. Denise Vieira <em>(duración: 96’)</em></p>
  <a href="{DIA_4}">ENTRADAS</a>
</div>
"""

fin_de_semana = parsear(FESTIVAL, hoy="2026-09-10")

# Cada película en SU día y a SU hora. La que rompía es Ramón Vázquez: sábado
# 12 a las 20.45, no domingo 13 a las 18.
assert [(f["fecha"], f["hora"], f["title"]) for f in fin_de_semana] == [
    ("2026-09-12", "19:15", "LOS CRUCES"),
    ("2026-09-12", "20:45", "RAMÓN VÁZQUEZ"),
    ("2026-09-13", "19:30", "Cortos II"),
    ("2026-09-13", "20:30", "SABES DE MIM AGORA ESQUEÇA"),
], fin_de_semana
print("✓ cada función queda en el día y la hora de su jornada")

# Director y duración son los de cada ficha, no los del vecino.
assert [(f["director"], f["duration"]) for f in fin_de_semana] == [
    ("Julián Galay", 71),
    ("Gustavo Fontán", 68),
    ("", None),
    ("Denise Vieira", 96),
], fin_de_semana
print("✓ director y duración salen de la ficha de cada película")

# El botón de entradas es uno por jornada: lo comparten todas sus funciones.
assert [f["ticket_url"] for f in fin_de_semana] == [DIA_3, DIA_3, DIA_4, DIA_4], \
    fin_de_semana
print("✓ las funciones de una jornada comparten el link de entradas")

# La charla de apertura no es una función de cine.
assert not [f for f in fin_de_semana if "conversaci" in f["title"].lower()], \
    fin_de_semana
assert not [f for f in fin_de_semana if f["hora"] == "18:00"], fin_de_semana
print("✓ la conversación de las 18 H no se publica como película")

# Con la ventana arrancando el domingo, el sábado ya pasó y no queda nada suyo.
domingo = parsear(FESTIVAL, hoy="2026-09-13")
assert [(f["fecha"], f["hora"], f["title"]) for f in domingo] == [
    ("2026-09-13", "19:30", "Cortos II"),
    ("2026-09-13", "20:30", "SABES DE MIM AGORA ESQUEÇA"),
], domingo
print("✓ una jornada fuera de la ventana no contagia su fecha a la otra")


# --- La ficha suelta de siempre: la fecha va DESPUÉS del "Dir.". ------------
FICHA = """
<div class="elementor-column">
  <h3>EL ESPEJO SOBRE LA LUNA</h3>
  <p>Dir. Leandro Katz<br/>
     Viernes 19 de septiembre, 20 H<br/>
     +<br/>
     Sábado 27 de septiembre, 19.30 H</p>
  <p>Un ensayo sobre las ruinas mayas <em>(duración: 100’)</em></p>
  <a href="https://www.alternativateatral.com/obra102424-el-espejo">entradas</a>
</div>
"""

espejo = parsear(FICHA, hoy="2026-09-13")
assert [(f["fecha"], f["hora"]) for f in espejo] == [
    ("2026-09-19", "20:00"), ("2026-09-27", "19:30"),
], espejo
assert {f["title"] for f in espejo} == {"EL ESPEJO SOBRE LA LUNA"}, espejo
assert {f["director"] for f in espejo} == {"Leandro Katz"}, espejo
assert {f["duration"] for f in espejo} == {100}, espejo
assert {f["ticket_url"] for f in espejo} == \
    {"https://www.alternativateatral.com/obra102424-el-espejo"}, espejo
print("✓ la ficha suelta sigue dando sus dos funciones con sus propios datos")

# Dos fichas sueltas en la misma sección no se mezclan las fechas ni los links.
DOS_FICHAS = """
<div class="elementor-column">
  <h3>LA FUNDACIÓN</h3>
  <p>Dir. Lucas Gallo<br/>
     Jueves 18 de septiembre, 20 H</p>
  <p>Archivo y política <em>(duración: 105’)</em></p>
  <a href="https://entradas.ar/fundacion">entradas</a>
</div>
<div class="elementor-column">
  <h3>LOS DÍAS CHINOS</h3>
  <p>Dir. Silvia Esteve<br/>
     Sábado 20 de septiembre, 19.30 H</p>
  <p>Un diario filmado <em>(duración: 89’)</em></p>
  <a href="https://entradas.ar/los-dias-chinos">entradas</a>
</div>
"""

dos = parsear(DOS_FICHAS, hoy="2026-09-13")
assert [(f["fecha"], f["hora"], f["title"], f["director"], f["duration"])
        for f in dos] == [
    ("2026-09-18", "20:00", "LA FUNDACIÓN", "Lucas Gallo", 105),
    ("2026-09-20", "19:30", "LOS DÍAS CHINOS", "Silvia Esteve", 89),
], dos
assert [f["ticket_url"] for f in dos] == [
    "https://entradas.ar/fundacion", "https://entradas.ar/los-dias-chinos"], dos
print("✓ dos fichas sueltas conservan cada una su fecha, su link y sus datos")

# Ciclo de una sola película: el nombre del ciclo y la película comparten
# sección y quedan DOS encabezados antes del "Dir." en vez de uno.
CICLO_UNA = """
<div class="elementor-column">
  <h3>Cine Fri: la película gratuita del mes</h3>
  <h3>1982</h3>
  <p>Dir. Mariano Donoso Makowski y Federico Cardone<br/>
     Viernes 26 de septiembre, 20 H</p>
  <p>Malvinas en el archivo <em>(duración: 75’)</em></p>
  <a href="https://entradas.ar/1982">entradas</a>
</div>
"""

fri = parsear(CICLO_UNA, hoy="2026-09-13")
assert [(f["fecha"], f["hora"], f["title"], f["ciclo"]) for f in fri] == [
    ("2026-09-26", "20:00", "1982", "Cine Fri: la película gratuita del mes"),
], fri
print("✓ el encabezado de más arriba de la ficha sigue siendo el ciclo")

# Una ficha con la fecha ARRIBA del título (sin líneas de hora) no es una
# jornada: es una película sola y se publica con el horario de esa fecha.
FECHA_ARRIBA = """
<div class="elementor-column">
  <p>Jueves 25 de septiembre, 20 H</p>
  <h3>LA MEMORIA DEL AGUA</h3>
  <p>Dir. Ana Poliak<br/>
     Un retrato del río <em>(duración: 82’)</em></p>
  <a href="https://entradas.ar/memoria">entradas</a>
</div>
"""

agua = parsear(FECHA_ARRIBA, hoy="2026-09-13")
assert [(f["fecha"], f["hora"], f["title"], f["director"], f["duration"])
        for f in agua] == [
    ("2026-09-25", "20:00", "LA MEMORIA DEL AGUA", "Ana Poliak", 82),
], agua
# Y la fecha de arriba no se cuela como nombre del ciclo.
assert [f["ciclo"] for f in agua] == [""], agua
print("✓ una ficha con la fecha arriba del título también sale publicada")


# --- La página entera, recorriendo secciones como scrape_arthaus. -----------
# Sin red: se le cambia el fetch_html y el date.today() al módulo.
import scraper

PAGINA = f"""
<section class="elementor-top-section">
  <h2>Quizás, quizás, quizás</h2>
  <p>Ciclo de cine</p>
</section>
<section class="elementor-top-section">{FESTIVAL}</section>
<section class="elementor-top-section">{CICLO_UNA}</section>
"""


class _Hoy(date):
    @classmethod
    def today(cls):
        return date(2026, 9, 13)


_fetch, _date = scraper.fetch_html, scraper.date
try:
    scraper.fetch_html = lambda url: BeautifulSoup(PAGINA, "html.parser")
    scraper.date = _Hoy
    pagina = sorted(scraper.scrape_arthaus(semanas=3),
                    key=lambda s: (s.fecha, s.hora))
finally:
    scraper.fetch_html, scraper.date = _fetch, _date

assert [(s.fecha, s.hora, s.title, s.ciclo) for s in pagina] == [
    ("2026-09-13", "19:30", "Cortos II", "Quizás, quizás, quizás"),
    ("2026-09-13", "20:30", "SABES DE MIM AGORA ESQUEÇA", "Quizás, quizás, quizás"),
    ("2026-09-26", "20:00", "1982", "Cine Fri: la película gratuita del mes"),
], pagina
print("✓ la página entera sale bien y la carátula de ciclo baja a su sección")

# El ciclo de la carátula de la sección baja a todas sus películas.
con_ciclo = parsear(FESTIVAL, hoy="2026-09-13", ciclo="Quizás, quizás, quizás")
assert {f["ciclo"] for f in con_ciclo} == {"Quizás, quizás, quizás"}, con_ciclo
print("✓ el ciclo de la sección llega a las funciones de la jornada")

print("✓ OK")
