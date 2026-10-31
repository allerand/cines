#!/usr/bin/env python3
"""
Test local de los scrapers de Madrid, sin red:

    python3 test_madrid.py

El texto del programa, las tarjetas de la boletería y el JSON de Yelmo son los
reales del 22/9/2026, recortados a lo que usa el scraper.
"""
from datetime import date

from scraper import (CINES_MADRID, DORE_PROYECCIONES, _callao_funciones,
                     _cba_funciones, _cineteca_ficha, _dore_arreglar_kerning,
                     _dore_combinar, _dore_programa, _dore_tarjetas,
                     _embajadores_funciones, _golem_ficha, _golem_funciones,
                     _ideal_funciones, _madrid_es_cine, _madrid_titulo_y_ciclo,
                     _metropol_funciones, _reina_actividades, _reina_ciclo_en_boleteria,
                     _reina_funciones, _reina_links_de_compra, _reina_programa,
                     _renoir_funciones, _equis_mes, _equis_programa,
                     _equis_titulo_y_ciclo, _equis_en_taquilla, _equis_ficha)

assert CINES_MADRID == {"Cine Doré", "Cines Ideal", "Cineteca Madrid",
                        "Cines Princesa", "Renoir Plaza de España", "Renoir Retiro",
                        "Golem Madrid", "Embajadores Glorieta", "Embajadores Ercilla",
                        "Artistic Metropol", "Cine Estudio", "Cines Callao",
                        "Museo Reina Sofía", "Sala Equis"}

# --- Programa del mes (texto de pypdf) ---------------------------------------
PROGRAMA = """\
PROGRAMA   PROGRAMA   PROGRAMA   PROGRAMA   PROGRAMA   PROGRAMA   PROGRAMA
DEL 24 AL 30
MIRADAS PROYECTADAS SALAS Y ESPECTADORES: ENCUENTROS A OSCURAS · ANDRZEJ WAJDA ENTRE
EL MITO Y LA HISTORIA · HONG KONG LOS AÑOS DEL NEÓN · HOMENAJE ADOLFO ARISTARAIN HUMANISMO
DOMINGO 27
ANDRZEJ WAJDA. ENTRE EL MITO Y LA HISTORIA HONG KONG. LOS AÑOS DE NEÓN
CENIZAS Y DIAMANTES
ANDRZEJ WAJDA, 1958
17:30 H · SALA 1 · 103’
DCP . REST. VOSE. COLOR
MY HEART IS THAT ETERNAL ROSE
PATRICK TAM, 1989
21:00 H · SALA 1 · 90’
DCP . VOSE. COLOR
MARTES 22
ANDRZEJ WAJDA MIRADAS PROYECTADAS
EVERYTHING FOR SALE
ANDRZEJ WAJDA, 1969
17:30 H · SALA 1 · 105’
DCP . VOSE*. COLOR
AUDIENCE + SHIRIN
BARBARA HAMMER, 2026;
ABBAS KIAROSTAMI, 2008
20:00 H · SALA 2 · 32', 90’
DCP . VOSE. B/N, COLOR
JUEVES 24
MIRADAS PROYECTADAS ANDRZEJ WAJDA HOMENAJE ADOLFO ARISTARAIN
TALKING ABOUT TREES
SUHAIB GASMELBARI, 2019
17:30 H · SALA 1 · 93’
DCP . VOSE*. COLOR
PAISAJE DESPUÉS DE
LA BATALLA
ANDRZEJ WAJDA, 1970
19:00 H · SALA 2 · 109’
DCP . REST. VOSE. COLOR
VIERNES 4
MIRADAS PROYECTADAS FUERA DE RADAR ANDRZEJ WAJDA
 LA ROSA PÚRPURA
 DE EL CAIRO
WOODY ALLEN, 1985
17:30 H · SALA 1 · 82’
35MM. VOSE. COLOR
RETRATOS F ANTASMA
KLEBER MENDONÇA FILHO, 2003
 19:00 H             ·SALA2 · 93
DCP . VOSE. B/N, COLOR
X30. Sesión con presentación
"""

prog = _dore_programa(PROGRAMA, 2026, 9)
por_clave = {(p["fecha"], p["hora"]): p for p in prog}
assert len(prog) == 8, prog

p = por_clave[("2026-09-27", "21:00")]
assert p["titulo"] == "MY HEART IS THAT ETERNAL ROSE"
assert p["fichas"] == [("PATRICK TAM", 1989)] and p["duracion"] == 90
print("✓ programa: título, ficha, hora y duración de cada sesión")

p = por_clave[("2026-09-22", "20:00")]
assert p["titulo"] == "AUDIENCE + SHIRIN"
assert p["fichas"] == [("BARBARA HAMMER", 2026), ("ABBAS KIAROSTAMI", 2008)]
assert p["duracion"] == 122
print("✓ programa doble: las dos fichas, y la duración es la de la sesión entera")

assert por_clave[("2026-09-24", "19:00")]["titulo"] == "PAISAJE DESPUÉS DE LA BATALLA"
print("✓ un título de dos líneas que no es el primero del día se lee entero")

assert por_clave[("2026-09-27", "17:30")]["titulo"] == "CENIZAS Y DIAMANTES"
assert por_clave[("2026-09-04", "17:30")]["titulo"] == ""
print("✓ primera sesión del día: con una línea de ciclos se lee; si es ambigua, queda vacía")

assert por_clave[("2026-09-04", "19:00")]["titulo"] == "RETRATOS FANTASMA"
assert _dore_arreglar_kerning("V ARIETY") == "VARIETY"
assert _dore_arreglar_kerning("MIRAGES DE PARIS") == "MIRAGES DE PARIS"
assert _dore_arreglar_kerning("WOLF AT THE DOOR") == "WOLF AT THE DOOR"
print("✓ kerning: 'F ANTASMA' → 'FANTASMA'; los títulos de verdad quedan igual")


# --- Boletería ---------------------------------------------------------------
def tarjeta(fecha, titulo, director, cuando, slug, a_la_venta):
    compra = (f'<a href="https://entradasfilmoteca.sacatuentrada.es/es/entradas/{slug}/{fecha}"'
              f' class="x">Comprar</a>') if a_la_venta else ""
    return f"""
    <div class="col s12" data-fecha="{fecha}" data-dia="22" data-mes="Septiembre">
      <div class="info col s12">
        <h2 class="titulo font-bold">{titulo}</h2>
        <h3 class="subtitulo font-bold">{director}</h3>
        <div class="descripcion"><div><strong>Fecha y Hora:</strong> {cuando}</div><div><br></div>
          <div>*Aunque las entradas aparezcan como agotadas en web, pueden adquirirse en taquilla</div></div>
      </div>
      <a href="https://entradasfilmoteca.sacatuentrada.es/es/productos/descripcion/{slug}">+&nbsp;INFO</a>
      {compra}
    </div>"""


BOLETERIA = "".join([
    """<div class="col s12" data-fecha="2000-01-01"><h2 class="titulo">BONO 10 FILMOTECA</h2>
       <div class="descripcion">PRECIOS REDUCIDOS</div></div>""",
    tarjeta("2026-09-22", "Everything for Sale (1969)", "Andrzej Wajda",
            "Martes 22 de septiembre a las 17:30h (Sala 1. Andrzej Wajda. Entre el mito y la historia)",
            "everything-for-sale-22-sep", True),
    tarjeta("2026-09-22", "Shirin (2008)", "Abbas Kiarostami",
            "Martes 22 de septiembre a las 20:00h (Sala 1. Miradas proyectadas. Salas y espectadores: Encuentros a oscuras)",
            "shirin-22-sep", True),
    # Sin venta abierta y con la hora mal: el programa dice 21:00.
    tarjeta("2026-09-27", "My Heart is That Eternal Rose (1989)", "Patrick Tam",
            ": Domingo 27 de septiembre a las 20:00h (Sala 1. Hong Kong. Los años del neón)",
            "my-heart-is-that-eternal-rose-27-sep", False),
    # Octubre, sin programa todavía.
    tarjeta("2026-10-02", "Ashes of Time (1994)", "Wong Kar-Wai",
            "Viernes 2 de octubre a las 20:00h (Sala 1. Hong Kong. Los años del neón)",
            "ashes-of-time", False),
    tarjeta("2026-10-03", "The Killer (1989)", "John Woo",
            "Sábado 3 de octubre a las 19:00h (Sala 2. Hong Kong. Los años del neón)",
            "the-killer-3-oct", True),
])

tarjetas = _dore_tarjetas(BOLETERIA)
assert [t["titulo"] for t in tarjetas] == [
    "Everything for Sale", "Shirin", "My Heart is That Eternal Rose", "Ashes of Time", "The Killer"]
t = tarjetas[0]
assert (t["fecha"], t["hora"], t["anio"], t["director"]) == ("2026-09-22", "17:30", 1969, "Andrzej Wajda")
assert t["ciclo"] == "Andrzej Wajda. Entre el mito y la historia"
assert t["url"].endswith("/entradas/everything-for-sale-22-sep/2026-09-22") and t["a_la_venta"]
assert tarjetas[2]["hora"] == "20:00" and not tarjetas[2]["a_la_venta"]
assert tarjetas[2]["url"].endswith("/productos/descripcion/my-heart-is-that-eternal-rose-27-sep")
print("✓ boletería: los bonos no son sesiones; título sin el año, ciclo sin la sala, link de compra o de la ficha")


# --- Las dos fuentes juntas --------------------------------------------------
funciones = _dore_combinar(tarjetas, prog, {(2026, 9)})
por = {(s.fecha, s.title): s for s in funciones}

s = por[("2026-09-27", "My Heart is That Eternal Rose")]
assert s.hora == "21:00" and s.duration == 90
print("✓ la hora del programa manda sobre la de la boletería (20:00 → 21:00)")

s = por[("2026-09-22", "Shirin")]
assert (s.hora, s.director, s.year, s.duration) == ("20:00", "Abbas Kiarostami", 2008, 122)
assert s.ciclo.startswith("Miradas proyectadas")
assert ("2026-09-22", "AUDIENCE + SHIRIN") not in por
print("✓ 'Shirin' de la boletería es 'AUDIENCE + SHIRIN' del programa: una sola función, con los datos de la boletería")

assert ("2026-10-03", "The Killer") in por
assert ("2026-10-02", "Ashes of Time") not in por
print("✓ sin programa del mes: entra lo que está a la venta, no lo que tiene la hora sin confirmar")

s = por[("2026-09-24", "PAISAJE DESPUÉS DE LA BATALLA")]
assert (s.hora, s.director, s.year, s.ticket_url) == ("19:00", "ANDRZEJ WAJDA", 1970, DORE_PROYECCIONES)
assert ("2026-09-04", "") not in por
print("✓ lo del programa que la boletería no cargó entra igual (salvo si el título quedó vacío)")

assert len(funciones) == len({(s.fecha, s.hora) for s in funciones})
print("✓ ninguna sesión sale dos veces")


# --- Cines Ideal (JSON de Yelmo) ---------------------------------------------
def peli(titulo, tipo, sesiones, director="Christopher Nolan", runtime="173"):
    return {"Title": titulo, "ProjectionType": tipo, "Director": director, "RunTime": runtime,
            "Formats": [{"Language": "INGLÉS SUBTITULADO EN ESPAÑOL (VOSE)",
                         "Showtimes": [{"Time": h, "ShowtimeId": i, "VistaCinemaId": "780"}
                                       for h, i in sesiones]}]}


YELMO = {"d": {"Cinemas": [
    {"Key": "la-vaguada", "VistaId": "1310", "Dates": [
        {"ShowtimeDate": "22 septiembre", "Movies": [peli("La odisea", "Movie", [("18:00", "1")])]}]},
    {"Key": "ideal", "VistaId": "780", "Dates": [
        {"ShowtimeDate": "21 septiembre", "Movies": [peli("La odisea", "Movie", [("18:20", "9")])]},
        {"ShowtimeDate": "22 septiembre", "Movies": [
            peli("La odisea", "Movie", [("18:20", "36088"), ("22:00", "36089")]),
            peli("MACBETH (Verdi) - MET LIVE 26-27", "Ópera", [("19:00", "5")], director="", runtime="209"),
            peli("OASIS: DON´T LOOK BACK IN ANGER", "Eventos Especiales", [("20:30", "7")],
                 director="Will  Lovelace", runtime="122"),
        ]},
        {"ShowtimeDate": "08 enero", "Movies": [peli("Dune: Parte Tres", "Movie", [("20:00", "8")])]},
    ]},
]}}

ideal = _ideal_funciones(YELMO, date(2026, 9, 22), date(2027, 3, 1))
assert [(s.fecha, s.hora, s.title) for s in ideal] == [
    ("2026-09-22", "18:20", "La odisea"),
    ("2026-09-22", "22:00", "La odisea"),
    ("2026-09-22", "20:30", "OASIS: DON´T LOOK BACK IN ANGER"),
    ("2027-01-08", "20:00", "Dune: Parte Tres"),
], [(s.fecha, s.hora, s.title) for s in ideal]
assert all(s.cine == "Cines Ideal" for s in ideal)
print("✓ ideal: sólo el Ideal, sin ayer ni la ópera; 'enero' es del año que viene")

s = ideal[0]
assert s.ticket_url == "https://compra.yelmocines.es/?cinemaVistaId=780&showtimeVistaId=36088"
assert (s.director, s.duration) == ("Christopher Nolan", 173)
assert ideal[2].director == "Will Lovelace"
print("✓ ideal: link directo a la compra de la sesión, director y duración")


# --- Cineteca Madrid ---------------------------------------------------------
# El HTML real de una actividad, recortado: ficha, y pases de dos meses con un
# día de dos horarios.
CINETECA_HTML = """
<div class="node node--type-activity">
  <div class="field field-name-dynamic-token-fieldnode-ciclo-copia"><a href="/ciclo/foco-pedro-pinho">FOCO: PEDRO PINHO</a></div>
  <div class="field field-name-field-parent-section"><span class="fCategory"><a href="/secciones/estrenos">ESTRENOS</a></span></div>
  <div class="field field-name-node-title"><h2 class="title">La risa y la navaja (versión integral)</h2></div>
  <div class="field field--name-field-original-title field__item"><span>(</span>O Riso e a Faca<span>)</span></div>
  <div class="field field--name-field-director field__item">Pedro Pinho</div>
  <div class="field field--name-field-pais field__item">Portugal, Brasil, Francia, Rumanía</div>
  <div class="field field--name-field-ano-filmacion field__item">2025</div>
  <div class="field field-name-field-duration"><span>(330')</span></div>
  <div class="field field--name-field-sessions sb-sessions">
    <div class="field__label sb-sessions__label">Pases:</div>
    <div class="sb-sessions__items">
      <h2 class="sb-sessions__date-month">Octubre</h2>
      <h4 class="sb-sessions__date-day">Jueves 1</h4>
      <ul class="sb-sessions__date-hours">
        <li class="sb-sessions__date-hours-hour">17:00 h</li>
        <li class="sb-sessions__date-hours-space">Sala Azcona</li>
        <li class="sb-sessions__date-hours-hour">21:30 h</li>
        <li class="sb-sessions__date-hours-space">Sala Plató</li>
      </ul>
      <h4 class="sb-sessions__date-day">Sábado 3</h4>
      <ul class="sb-sessions__date-hours">
        <li class="sb-sessions__date-hours-hour">17:00 h</li>
        <li class="sb-sessions__date-hours-space">Sala Azcona</li>
      </ul>
      <h2 class="sb-sessions__date-month">Noviembre</h2>
      <h4 class="sb-sessions__date-day">Domingo 8</h4>
      <ul class="sb-sessions__date-hours">
        <li class="sb-sessions__date-hours-hour">20:00 h</li>
        <li class="sb-sessions__date-hours-space">Sala Borau</li>
      </ul>
      <h2 class="sb-sessions__date-month">Enero</h2>
      <h4 class="sb-sessions__date-day">Viernes 9</h4>
      <ul class="sb-sessions__date-hours">
        <li class="sb-sessions__date-hours-hour">19:00 h</li>
      </ul>
    </div>
  </div>
</div>
"""

URL_CT = "https://www.cinetecamadrid.com/programacion/la-risa-y-la-navaja-version-integral"
ct = _cineteca_ficha(CINETECA_HTML, URL_CT, date(2026, 10, 1), date(2026, 12, 3))
assert [(s.fecha, s.hora) for s in ct] == [
    ("2026-10-01", "17:00"), ("2026-10-01", "21:30"), ("2026-10-03", "17:00"),
    ("2026-11-08", "20:00")], [(s.fecha, s.hora) for s in ct]
print("✓ cineteca: un día con dos pases, dos meses seguidos, y enero queda fuera de la ventana")

s = ct[0]
assert s.cine == "Cineteca Madrid" and s.title == "La risa y la navaja (versión integral)"
assert (s.director, s.year, s.duration) == ("Pedro Pinho", 2025, 330)
assert s.original_title == "O Riso e a Faca"
assert s.country == "Portugal, Brasil, Francia, Rumanía"
assert s.ciclo == "FOCO: PEDRO PINHO" and s.ticket_url == URL_CT
print("✓ cineteca: título original, director, país, año y duración de la ficha")

assert _cineteca_ficha("<div>nada</div>", URL_CT, date(2026, 10, 1), date(2026, 12, 3)) == []
print("✓ cineteca: una página sin ficha no inventa funciones")


# --- Renoir ------------------------------------------------------------------
# El mismo pase va dos veces en el HTML: el bloque de escritorio y el de móvil.
def _renoir_bloque():
    return """
    <div class="my-account-content"><div class="row">
      <div class="col-4"><a href="/pelicula/bad-apples/">BAD APPLES</a>
        <br><small><b> de Jonatan Etzler </b></small>
        <br><small>Versión Original subtitulada a Castellano</small>
        <br><small> Duración 100 minutos </small>
        <br><small>No recomendada para menores de 16 años</small>
      </div>
      <div class="col-7">
        <div class="pase-cartelera"><span>sala 07</span>
          <span><a href="https://www.pillalas.com/pase/1089142/" class="btn">16:00</a></span></div>
        <div class="pase-cartelera"><span>sala 07</span>
          <span><a href="https://www.pillalas.com/pase/1089144/" class="btn">18:00</a></span></div>
      </div>
    </div></div>"""


renoir = _renoir_funciones(_renoir_bloque() + _renoir_bloque(), "Cines Princesa", "2026-09-28")
assert [(s.hora, s.title) for s in renoir] == [("16:00", "BAD APPLES"), ("18:00", "BAD APPLES")]
assert renoir[0].ticket_url == "https://www.pillalas.com/pase/1089142/"
assert (renoir[0].director, renoir[0].duration) == ("Jonatan Etzler", 100)
assert renoir[0].cine == "Cines Princesa"
print("✓ renoir: cada pase una sola vez (el id manda), con su butaca, director y duración")


# --- Cines Embajadores -------------------------------------------------------
def _emb_pase(direccion, dia, hora, id_):
    return (f'<p data-direccion="{direccion}" data-sala="Emb1" data-dia="{dia}" data-hora="{hora}">'
            f'<a class="compraTicket" href="https://www.reservaentradas.com/entrada/madrid/'
            f'cineembajadores/la-bola-negra/{id_}/">{hora}</a></p>')


EMB_HTML = """
<ul class="cartelera"><li class="movie">
  <div class="info"><h2><a href="https://cinesembajadores.es/pelicula/la-bola-negra/">La bola negra</a></h2>
    <ul class="buttons"><li class="minutos">159 min.</li><li class="doblaje">V.E.</li></ul>
    <div class="more"><h5><strong>Dirección</strong>:Javier Ambrossi, Javier Calvo</h5>
      <h5><strong>Reparto</strong>:Penélope Cruz</h5></div>
  </div>
  <div class="tabla-horarios">""" + \
    _emb_pase("Gta. Sta. Mª de la Cabeza", "28/09", "16:00", "38660") + \
    _emb_pase("Calle Ercilla, 53", "28/09", "19:40", "38736") + \
    _emb_pase("Calle Ercilla, 53", "15/12", "20:00", "39999") + \
    _emb_pase("Calle Corrida, 1", "29/09", "20:00", "40000") + """
  </div></li></ul>"""

emb = _embajadores_funciones(EMB_HTML, date(2026, 9, 28), date(2026, 11, 30))
assert [(s.cine, s.fecha, s.hora) for s in emb] == [
    ("Embajadores Glorieta", "2026-09-28", "16:00"),
    ("Embajadores Ercilla", "2026-09-28", "19:40")], [(s.cine, s.fecha, s.hora) for s in emb]
assert emb[0].director == "Javier Ambrossi, Javier Calvo" and emb[0].duration == 159
assert emb[1].ticket_url.endswith("/38736/")
print("✓ embajadores: cada pase a su sala; fuera de la ventana y sala de otra ciudad no entran")


# --- Golem -------------------------------------------------------------------
GOLEM_HTML = """
<table>
 <tr><td><a href="/golem/pelicula/Vivir-la-tierra-(V.O.S.E.)" class="txtNegXXL">Vivir la tierra (V.O.S.E.)</a></td></tr>
 <tr><td><a href="/golem/urlcheck.php?idCine=8&perfCode=99986&eventCode=115025" class="horaXXXL">21:00</a>
         <a href="/golem/urlcheck.php?idCine=8&perfCode=99987&eventCode=115025" class="horaTexto">Comprar</a></td></tr>
 <tr><td><a href="/golem/pelicula/La-bola-negra" class="txtNegXXL">La bola negra</a></td></tr>
 <tr><td><a href="/golem/urlcheck.php?idCine=8&perfCode=99896&eventCode=112109" class="horaXXXL">16:10</a></td></tr>
</table>"""

golem = _golem_funciones(GOLEM_HTML, "2026-09-28")
assert [(slug.split("/")[-1], f.hora, f.title) for slug, f in golem] == [
    ("Vivir-la-tierra-(V.O.S.E.)", "21:00", "Vivir la tierra"),
    ("La-bola-negra", "16:10", "La bola negra")], golem
assert golem[0][1].ticket_url.startswith("https://www.golem.es/golem/urlcheck.php")
print("✓ golem: la hora se le cuelga al último título, y (V.O.S.E.) no es parte del nombre")

GOLEM_FICHA = """<div>Ficha Técnica:
 Título original: Sheng xi zhi di
 Dirigida por: Huo Meng
 Duración: 132 min.
 Nacionalidad: CHINA
 Sinopsis: En 1991…</div>"""
assert _golem_ficha(GOLEM_FICHA) == {"original_title": "Sheng xi zhi di", "director": "Huo Meng",
                                     "duration": 132, "country": "China"}
print("✓ golem: la ficha de la película, con el país en minúsculas de las de siempre")


# --- Versiones y ciclos pegados al título ------------------------------------
casos = [
    ("Tiempo de victoria (VOSE)",                 ("Tiempo de victoria", "")),
    ("Cinco segundos (DOBLADA AL ESPAÑOL)",       ("Cinco segundos", "")),
    ("El ser querido (OCAP)",                     ("El ser querido", "")),
    ("Vivir la tierra (V.O.S.E.)",                ("Vivir la tierra", "")),
    ("Suspiria [wilder Cinema]",                  ("Suspiria", "Wilder cinema")),
    ("Las Culpables [docs del Mes]",              ("Las Culpables", "Docs del mes")),
    ("SESIÓN TETA: La bola negra",                ("La bola negra", "Sesión teta")),
    ("Domingo de clásicos: El hombre tranquilo (VOSE)",
                                                  ("El hombre tranquilo", "Domingo de clásicos")),
    # Un título con dos puntos que NO es un ciclo se queda como está.
    ("Spider-Man: Brand New Day",                 ("Spider-Man: Brand New Day", "")),
    ("La odisea",                                 ("La odisea", "")),
]
for entrada, esperado in casos:
    assert _madrid_titulo_y_ciclo(entrada) == esperado, (entrada, _madrid_titulo_y_ciclo(entrada))
assert _madrid_titulo_y_ciclo("Suspiria [wilder Cinema]", "Halloween") == ("Suspiria", "Halloween")
print("✓ título y ciclo: la versión se cae, el ciclo va a su columna y 'Spider-Man:' no se parte")

assert not _madrid_es_cine("Manon (Ballet EN DIRECTO desde The Royal Ballet)")
assert not _madrid_es_cine("L’elisir D’amore (Ópera EN DIFERIDO desde la Ópera Estatal de Viena)")
assert not _madrid_es_cine("Concierto Pavarotti 90th – The Grand Tribute")
assert not _madrid_es_cine("BTS WORLD TOUR ARIRANG: LIVE VIEWING")
assert _madrid_es_cine("El concierto") and _madrid_es_cine("La ópera de los tres centavos")
print("✓ la ópera y el ballet en directo no entran; una película con 'concierto' u 'ópera' en el título, sí")

# La marca de versión también viene suelta, sin paréntesis (Artistic Metropol).
assert _madrid_titulo_y_ciclo("PATRICK V.O.S.E.") == ("PATRICK", "")
assert _madrid_titulo_y_ciclo("PALESTINA 36 Doblada al español") == ("PALESTINA 36", "")
print("✓ la versión suelta al final también se cae")


# --- Artistic Metropol (API de eventos) --------------------------------------
METROPOL = [
    {"title": "SALA 1: PALESTINA 36 (2025) Doblada al español", "start_date": "2026-09-29 17:50:00",
     "url": "https://artisticmetropol.es/sesion/sala-1-palestina-36-2025-doblada-al-espanol-6/"},
    {"title": "SALA 2: Pase PRIVADO", "start_date": "2026-09-29 18:00:00", "url": "x"},
    {"title": "SALA 2: PATRICK (1978) V.O.S.E.", "start_date": "2026-09-29 16:00:00", "url": "y"},
    {"title": "SALA 1: AYER (2019)", "start_date": "2026-08-01 20:00:00", "url": "z"},
]
met = _metropol_funciones(METROPOL, date(2026, 9, 28), date(2026, 11, 30))
assert [(s.fecha, s.hora, s.title, s.year) for s in met] == [
    ("2026-09-29", "17:50", "PALESTINA 36", 2025),
    ("2026-09-29", "16:00", "PATRICK", 1978)], [(s.fecha, s.hora, s.title, s.year) for s in met]
assert met[0].cine == "Artistic Metropol"
print("✓ metropol: sala y versión fuera del título, el año adentro, y los pases privados no son cartelera")


# --- Cine Estudio (Círculo de Bellas Artes) ----------------------------------
CBA_HTML = """
<h1 class="fl-heading"><span class="fl-heading-text">Círculo de Bellas Artes de Madrid</span></h1>
<div class="fl-col-content">
  <h1 class="fl-heading"><span class="fl-heading-text">Anoche conquisté Tebas</span></h1>
  <h3 class="fl-heading"><span class="fl-heading-text">Gabriel Azorín</span></h3>
</div>
<a href="https://www.circulobellasartes.com/ciclos-cine/ciclos-de-cine/fid-marseille/">FID Marseille</a>
<table class="cba_tabla_sesiones"><tbody>
  <tr><td>Mié 23/09, 17:00</td><td>Precio reducido</td></tr>
  <tr><td>Sáb 03/10, 17:00</td><td></td></tr>
  <tr><td>Dom 04/10, 21:15</td><td></td></tr>
</tbody></table>"""

URL_CBA = "https://www.circulobellasartes.com/ciclos-cine/peliculas/anoche-conquiste-tebas/"
cba = _cba_funciones(CBA_HTML, URL_CBA, date(2026, 9, 28), date(2026, 11, 30))
assert [(s.fecha, s.hora) for s in cba] == [("2026-10-03", "17:00"), ("2026-10-04", "21:15")]
assert cba[0].title == "Anoche conquisté Tebas" and cba[0].director == "Gabriel Azorín"
assert cba[0].ciclo == "FID Marseille" and cba[0].cine == "Cine Estudio"
print("✓ cine estudio: el título es el de la película y no el del Círculo; la sesión pasada no entra")


# --- Cines Callao ------------------------------------------------------------
CALLAO_HTML = """
<div class="et_pb_column">
  <div><p style="text-align: center;">ESTRENO</p></div>
  <div><p style="text-align: center;"><strong>Spider-Man: Brand New Day</strong></p></div>
  <div>
    <p style="text-align: center;">Sábado<span> 26/09<strong> 15:50</strong></span></p>
    <p style="text-align: center;"><span><strong>_____</strong></span></p>
    <p style="text-align: center;">Lunes 28<span>/09<strong> 16:00, 19:00, 22:00</strong></span></p>
    <p style="text-align: center;"><span>Martes 29/09<strong> ---</strong></span></p>
  </div>
  <a href="https://www.reservaentradas.com/sesiones/madrid/callao/spiderman/">Comprar entradas</a>
</div>"""

callao = _callao_funciones(CALLAO_HTML, date(2026, 9, 28), date(2026, 11, 30))
assert [(s.fecha, s.hora) for s in callao] == [
    ("2026-09-28", "16:00"), ("2026-09-28", "19:00"), ("2026-09-28", "22:00")]
assert callao[0].title == "Spider-Man: Brand New Day"
assert callao[0].ticket_url.endswith("/callao/spiderman/")
print("✓ callao: los tres horarios del día, el día pasado y el '---' afuera")


# --- Museo Reina Sofía ---------------------------------------------------------
# El 'content' del page-data.json de las fichas reales (octubre de 2026),
# recortado a lo que usa el scraper. Las fechas son epoch: 1797012000 es el
# 11/12/2026 a las 19:00 de Madrid.
def reina_item(ts, titulo, descripcion):
    return {"entity": {"date": ts, "titleHtml": {"value": titulo},
                       "descriptionHtml": {"value": descripcion}}}


def reina_ficha(fechas, items, ciclo="<p>El presente en escena. Cine argentino del siglo XXI</p>"):
    return {"parent": {"entity": {"title": {"value": ciclo}}},
            "events": [{"entity": {"dates": [{"entity": {"date": ts}} for ts in fechas]}}],
            "schedule": items}


# Una sola película: director y título en el título del ítem, la ficha técnica
# en la descripción, y abajo la presentación, que no es una película.
CLARISA = reina_ficha([1797012000], [reina_item(
    1797012000, "<p>Clarisa Navas.<em> Las mil y una</em></p>",
    "<p>Argentina y Alemania, 2020, DCP, color, versión original en español, 120’&nbsp;</p>\n"
    "<p>—Con presentación en vídeo de Roger Koza, cocomisario del ciclo</p>\n")])
URL_CLARISA = "https://www.museoreinasofia.es/actividad/clarisa-navas-presente-escena-cine/"
clarisa = _reina_funciones(CLARISA, URL_CLARISA, date(2026, 10, 25), date(2026, 12, 27))
assert [(s.fecha, s.hora, s.title, s.director, s.year, s.duration) for s in clarisa] == [
    ("2026-12-11", "19:00", "Las mil y una", "Clarisa Navas", 2020, 120)], clarisa
assert clarisa[0].country == "Argentina y Alemania" and clarisa[0].cine == "Museo Reina Sofía"
assert clarisa[0].ciclo == "El presente en escena. Cine argentino del siglo XXI"
assert clarisa[0].ticket_url == URL_CLARISA
print("✓ reina sofía: una película, con su ficha técnica y sin la presentación")

# Programa doble de Portabella: la traducción entre corchetes es el título en
# español y el de <em> queda como original.
PORTABELLA = """<p>Programa</p>
<p><strong>Pere Portabella. </strong><em><strong>Mudanza</strong></em><br>España, 2008, DCP, color, sonido, versión original sin diálogos, 20’</p>
<p><strong>Pere Portabella.</strong> <em><strong>Die Stille vor Bach</strong></em> <strong>[El silencio antes de Bach]</strong><br>España, 2007, DCP, color, sonido, versión original en alemán, castellano, francés e italiano con subtítulos en español, 102’</p>"""
pelis = _reina_programa(PORTABELLA)
assert [(p["titulo"], p["traduccion"], p["director"], p["year"], p["duration"]) for p in pelis] == [
    ("Mudanza", "", "Pere Portabella", 2008, 20),
    ("Die Stille vor Bach", "El silencio antes de Bach", "Pere Portabella", 2007, 102)], pelis
portabella = _reina_funciones(reina_ficha([1792861200], [reina_item(1792861200, "<p>Programa</p>",
                                                                  PORTABELLA)]),
                              "u", date(2026, 10, 1), date(2026, 12, 1))
assert [(s.title, s.original_title) for s in portabella] == [
    ("Mudanza", ""), ("El silencio antes de Bach", "Die Stille vor Bach")], portabella
assert {(s.fecha, s.hora) for s in portabella} == {("2026-10-24", "19:00")}
print("✓ reina sofía: programa doble en dos filas; la traducción va de título")

# El punto pegado al título adentro del <em>, la ficha técnica en el párrafo
# de abajo y la sinopsis de los cortos de Proyector de luna.
VARIOS = """<p>—Con la presentación de Parastoo Anoushahpour</p>
<p><strong>Parastoo Anoushahpour, Faraz Anoushahpour y Ryan Ferko</strong><em><strong>. Lovers' Wind</strong></em><br>Canadá, Irán, Túnez, 2024, DCP, color, sonido, versión original en iraní e inglés con subtítulos en español e inglés, 36’</p>
<p><strong>Bette Gordon. </strong><em><strong>An Algorithm</strong></em><strong>&nbsp;</strong>&nbsp;</p>
<p>Estados Unidos, 1977, AD, color, sonido, versión original en inglés, 9'&nbsp;</p>
<p><strong>Lucio Álvarez.</strong> <em><strong>Reduce, reutiliza y recicla</strong></em><br>Argentina, 2022, AD, color, sonido, versión original en español, 2'44''</p>
<p>En la escuela se trabaja mucho con las consignas de las 3R, reducir, reutilizar y, sobre todo, reciclar. En 2022 grabaron 3' de canción.</p>
<p><strong>Jean-Luc Godard y Anne-Marie Miéville.</strong><em><strong> The Old Place</strong></em><strong>.&nbsp;</strong><em><strong>Small Notes Regarding the Arts at Fall of 20th Century</strong></em><br>Francia y Estados Unidos, 1999, AD, color, versión original en francés subtitulada en español, 49´. Copia remasterizada</p>"""
assert [(p["director"], p["titulo"], p["country"], p["year"], p["duration"])
        for p in _reina_programa(VARIOS)] == [
    ("Parastoo Anoushahpour, Faraz Anoushahpour y Ryan Ferko", "Lovers' Wind", "Canadá, Irán, Túnez", 2024, 36),
    ("Bette Gordon", "An Algorithm", "Estados Unidos", 1977, 9),
    ("Lucio Álvarez", "Reduce, reutiliza y recicla", "Argentina", 2022, 2),
    ("Jean-Luc Godard y Anne-Marie Miéville",
     "The Old Place. Small Notes Regarding the Arts at Fall of 20th Century",
     "Francia y Estados Unidos", 1999, 49),
]
print("✓ reina sofía: el punto del <em>, la ficha en otro párrafo y la sinopsis afuera")

# Sin películas en la agenda (los pases de Eli Cortiñas decían sólo "Primer
# pase"): no se inventa nada.
assert _reina_funciones(reina_ficha([1790269200, 1790874000], [
    reina_item(1790269200, "<p>Primer pase</p>", "<p>—Con la presentación de Eli Cortiñas&nbsp;</p>"),
    reina_item(1790874000, "<p>Segundo pase</p>", "")]), "u", date(2026, 9, 1), date(2026, 12, 1)) == []

# La misma película en dos fechas (el ítem de la agenda trae sólo la primera),
# y la primera ya pasó.
REPITE = reina_ficha([1790269200, 1790874000], [reina_item(
    1790269200, "<p>Jacques Deray<em>.</em> <em>La piscine</em> [La piscina]</p>",
    "<p>Francia, 1969, AD, color, sonido, versión original en francés con subtítulos en español, 120’. Copia restaurada en 4K</p>")])
repite = _reina_funciones(REPITE, "u", date(2026, 9, 30), date(2026, 12, 1))
assert [(s.fecha, s.hora, s.title, s.original_title, s.duration) for s in repite] == [
    ("2026-10-01", "19:00", "La piscina", "La piscine", 120)], repite
print("✓ reina sofía: sin programa no hay filas; un programa repetido va en cada fecha")

# El buscador: entra lo que tiene alguna fecha en la ventana.
BUSCADOR = [
    {"url": {"path": "/actividad/clarisa-navas-presente-escena-cine"},
     "processedDates": [{"value": "2026-12-11T19:00:00"}]},
    {"url": {"path": "/actividad/cine-pere-portabella-sesion-6"},
     "processedDates": [{"value": "2026-10-22T19:00:00"}]},
    {"url": {"path": "/actividad/albert-lamorisse-infancia-eterna-proyector-luna-10"},
     "processedDates": [{"value": "2026-10-18T12:00:00"}, {"value": "2026-10-25T12:00:00"}]},
    {"url": {"path": "/actividad/oculta"}, "hidden": True,
     "processedDates": [{"value": "2026-11-01T19:00:00"}]},
]
assert _reina_actividades(BUSCADOR, date(2026, 10, 25), date(2026, 12, 27)) == [
    "/actividad/clarisa-navas-presente-escena-cine",
    "/actividad/albert-lamorisse-infancia-eterna-proyector-luna-10"]
print("✓ reina sofía: del buscador, sólo las actividades con fechas por venir")


# El link de compra. El botón ENTRADAS de la ficha de la sesión 12 apuntaba a
# la función de Clarisa Navas (18371042): de ahí sale sólo el ciclo, y la
# función se busca en la boletería por hora y nombre. Los eventos son los que
# devolvía Clorian el 25/10/2026, recortados.
FICHA_MARTEL = "https://www.museoreinasofia.es/actividad/lucrecia-martel-maria-alche-benjamin-naishtat-presente-escena-cine/"
ciclo_martel = _reina_ciclo_en_boleteria({
    "title": {"value": "<p>Lucrecia Martel. <em>Camarera de piso</em> y María Alché y Benjamin Naishtat. <em>Pedro en el país</em></p>"},
    "tickets": [{"entity": {"url": {"url": {"path":
        "https://entradas.museoreinasofia.es/es/143-web-individual/"
        "14655-el-presente-en-escena-cine-argentino-del-siglo-xxi/18371042-clarisa-navas-las-mil-y-una"}}}}]})
assert ciclo_martel == {"grupo": "143-web-individual", "producto": "14655",
                        "slug": "el-presente-en-escena-cine-argentino-del-siglo-xxi",
                        "titulo": "Lucrecia Martel. Camarera de piso y María Alché y Benjamin Naishtat. Pedro en el país"}
EVENTOS = {"14655": [
    {"eventId": 18371042, "startDatetime": "2026-12-11T19:00+01:00",
     "name": "Clarisa Navas. Las mil y una    ", "slug": "clarisa-navas-las-mil-y-una"},
    {"eventId": 18371047, "startDatetime": "2026-12-12T18:00+01:00",
     "name": "Lucrecia Martel. Camarera de piso y Benjamin Naishatat y María Alche. Pedro en el País",
     "slug": "lucrecia-martel-camarera-de-piso-y-benjamin-naishatat-y-maria-alche-pedro-en-el-pais"},
    {"eventId": 18370572, "startDatetime": "2026-12-10T19:00+01:00",
     "name": "Hernán Roselli. Algo viejo, algo nuevo, algo prestado ",
     "slug": "hernan-roselli-algo-viejo-algo-nuevo-algo-prestado"},
]}
martel = _reina_funciones(reina_ficha([1797094800], [reina_item(
    1797094800, "<p>PROGRAMA</p>",
    "<p><strong>Lucrecia Martel. </strong><em><strong>Camarera de piso&nbsp;</strong></em><br>Argentina y México, 2022, AD, color, sonido, versión original en español, 12’&nbsp;</p>"
    "<p><strong>María Alché y Benjamín Naishtat. </strong><em><strong>Pedro en el país&nbsp;</strong></em><br>Argentina, México y Noruega, 2026, DCP, color, sonido versión original en español, 61’</p>")]),
    FICHA_MARTEL, date(2026, 10, 25), date(2026, 12, 27))
assert [(s.fecha, s.hora) for s in martel] == [("2026-12-12", "18:00")] * 2, martel
assert _reina_links_de_compra(martel, {FICHA_MARTEL: ciclo_martel}, EVENTOS) == 2
assert {s.ticket_url for s in martel} == {
    "https://entradas.museoreinasofia.es/es/143-web-individual/14655-el-presente-en-escena-cine-argentino-del-siglo-xxi/"
    "18371047-lucrecia-martel-camarera-de-piso-y-benjamin-naishatat-y-maria-alche-pedro-en-el-pais"}
print("✓ reina sofía: el link de compra es el de la función, no el que trae la ficha")

# Lo dudoso queda en la ficha: a esa hora la boletería tiene otra película, o
# dos funciones, o la boletería no cargó.
def reina_sesion(titulo, fecha, hora):
    from scraper import Screening
    return Screening(cine="Museo Reina Sofía", title=titulo, fecha=fecha, hora=hora,
                     ticket_url=FICHA_MARTEL)
otra = [reina_sesion("Otra película", "2026-12-12", "18:00")]
dos = [reina_sesion("Las mil y una", "2026-12-11", "19:00")]
caida = [reina_sesion("Las mil y una", "2026-12-11", "19:00")]
ciclo_sin_titulo = {**ciclo_martel, "titulo": ""}
assert _reina_links_de_compra(otra, {FICHA_MARTEL: ciclo_sin_titulo}, EVENTOS) == 0
assert _reina_links_de_compra(dos, {FICHA_MARTEL: ciclo_sin_titulo}, {"14655": EVENTOS["14655"] + [
    {"eventId": 1, "startDatetime": "2026-12-11T19:00+01:00", "name": "Las mil y una", "slug": "x"}]}) == 0
assert _reina_links_de_compra(caida, {FICHA_MARTEL: ciclo_sin_titulo}, {}) == 0
assert {s.ticket_url for s in otra + dos + caida} == {FICHA_MARTEL}
# Los cortos de Proyector de luna no se llaman como la función: coincide el
# nombre de la actividad.
corto = [reina_sesion("Beatles For Ever", "2026-10-25", "12:00")]
assert _reina_links_de_compra(corto, {FICHA_MARTEL: {
    "grupo": "143-web-individual", "producto": "14603", "slug": "proyector-de-luna",
    "titulo": "¡Silencio, se rueda! La infancia dirige 2"}}, {"14603": [
    {"eventId": 18269014, "startDatetime": "2026-10-25T12:00+01:00",
     "name": "¡Silencio, se rueda! La infancia dirige 2. Proyector de luna #11",
     "slug": "silencio-se-rueda-la-infancia-dirige-2-proyector-de-luna-11"}]}) == 1
assert corto[0].ticket_url.endswith("/14603-proyector-de-luna/18269014-silencio-se-rueda-la-infancia-dirige-2-proyector-de-luna-11")
print("✓ reina sofía: sin una sola función que coincida en hora y nombre, queda la ficha")

# --- Sala Equis: el PDF del mes (texto real de pypdf, noviembre de 2026) ------
EQUIS_PDF = """\
01 DOMINGO
17:30h: CINE POR MUJERES: VERANO 
1993
Carla Simón, 2017- VOSE- 97´
22h: BAD APPLES
Jonatan Etzler, 2025 - VOSE- 99’
03 MARTES
19.15h: JIM QUEEN
Marco Nguyen, Nicolas Athane, 2026 - 
VOSE- 83’
04 MIÉRCOLES
19.30h: MADLATIN: LA PLAYA DE LOS 
ENCHAQUIRADOS
Iván Mora Manzano, 2021 - VO- 86’
*Proyección con presentación y coloquio
07 SÁBADO
21h: FESTIVAL ANFIBIA: SESIÓN DE COR-
TOS: EL CUERPO DE CRISTO, DELINCUEN-
TE,  ROUGE Y CALM
09 LUNES
NO HAY SESIONES
16  LUNES
17h:  QUEERCINEMAD: A PAIXÂO SEGUN-
DO G.H.B
Gustavo Vinagre, Vinícius Couto, 2026 - 
VOSE- 92’
*Proyección con presentación
17  MARTES
19:30h: FESTIVAL RIZOMA
PROGRAMACIÓN    PROGRAMACIÓN    PROGRAMACIÓN    PROGRAMACIÓN
C/Duque de Alba, 4
11/2026
11/2026 
11/2026
"""
assert _equis_mes(EQUIS_PDF) == (2026, 11)
eq = _equis_programa(EQUIS_PDF, 2026, 11)
assert [(s["fecha"], s["hora"]) for s in eq] == [
    ("2026-11-01", "17:30"), ("2026-11-01", "22:00"), ("2026-11-03", "19:15"),
    ("2026-11-04", "19:30"), ("2026-11-07", "21:00"), ("2026-11-16", "17:00"),
    ("2026-11-17", "19:30")], eq
assert eq[0] == {"fecha": "2026-11-01", "hora": "17:30", "titulo": "CINE POR MUJERES: VERANO 1993",
                 "director": "Carla Simón", "anio": 2017, "duracion": 97}
assert (eq[2]["director"], eq[2]["duracion"]) == ("Marco Nguyen, Nicolas Athane", 83)
assert eq[4]["titulo"] == "FESTIVAL ANFIBIA: SESIÓN DE CORTOS: EL CUERPO DE CRISTO, DELINCUENTE, ROUGE Y CALM"
assert eq[5]["titulo"] == "QUEERCINEMAD: A PAIXÂO SEGUNDO G.H.B"
assert (eq[6]["titulo"], eq[6]["director"], eq[6]["anio"]) == ("FESTIVAL RIZOMA", "", None)
print("✓ sala equis: el PDF da día, hora, título de dos líneas y ficha")

# Con el mes equivocado no coincide ningún día de la semana y no entra nada.
assert _equis_programa(EQUIS_PDF, 2026, 10) == []
print("✓ sala equis: un PDF con el mes mal leído no se publica")

TAQUILLA = {"backrooms": "/backrooms/", "verano1993": "/verano-1993/",
            "aeternaequisbloodfeast": "/aeterna/", "eva": "/eva/",
            "pausavespertinebjork": "/pausa-bjork/",
            "pausainthecourtofthecrimsonking": "/pausa-crimson/",
            "laplayadelosenchaquirados": "/playa/"}
assert _equis_titulo_y_ciclo("CINE POR MUJERES: VERANO 1993", TAQUILLA) == ("VERANO 1993", "Cine Por Mujeres")
assert _equis_titulo_y_ciclo("MADLATIN: LA PLAYA DE LOS ENCHAQUIRADOS", TAQUILLA) == (
    "LA PLAYA DE LOS ENCHAQUIRADOS", "Madlatin")
assert _equis_titulo_y_ciclo("AETERNA: BLOOD FEAST", TAQUILLA) == ("BLOOD FEAST", "Aeterna")
assert _equis_titulo_y_ciclo("BACKROOMS: LIQUIDACIÓN TOTAL", TAQUILLA) == ("BACKROOMS: LIQUIDACIÓN TOTAL", "")
assert _equis_titulo_y_ciclo("MUJERES DE CINE: SESIÓN SORPRESA", TAQUILLA) == ("SESIÓN SORPRESA", "Mujeres de Cine")
assert _equis_titulo_y_ciclo("PAUSA: IN THE COURT OF CRIMSON KING (King Crimson)", TAQUILLA)[1] == "Pausa"
assert _equis_titulo_y_ciclo("CICLO LGBTIQ(X): LA CARN", TAQUILLA) == ("LA CARN", "Ciclo LGBTIQ(X)")
assert _equis_titulo_y_ciclo("FESTIVAL RIZOMA", TAQUILLA) == ("FESTIVAL RIZOMA", "")
assert _equis_en_taquilla("BACKROOMS: LIQUIDACIÓN TOTAL", TAQUILLA) == "/backrooms/"
assert _equis_en_taquilla("EVA", TAQUILLA) == "/eva/"
assert _equis_en_taquilla("EVANGELIO", TAQUILLA) == ""
print("✓ sala equis: el ciclo se separa sólo si lo de después de los dos puntos es la película")

FICHA_EQUIS = """<div class="woocommerce-product-details__short-description">
<a href="https://kinetike.com:83/views/sesionesFuturas.aspx?idPelicula=2969&cine=EQUIS" class="submit">Comprar</a>
<div class="shortDescription"><p class="p1">Javier Calvo y Javier Ambrossi / España / 2026</p>
<p class="p1">VO – 155 min</p></div></div>"""
assert _equis_ficha(FICHA_EQUIS) == {
    "compra": "https://kinetike.com:83/views/sesionesFuturas.aspx?idPelicula=2969&cine=EQUIS",
    "country": "España"}
print("✓ sala equis: de la ficha salen la compra y el país")

print("\nTodo OK")
