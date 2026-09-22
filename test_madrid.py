#!/usr/bin/env python3
"""
Test local de los scrapers de Madrid (Cine Doré y Cines Ideal), sin red:

    python3 test_madrid.py

El texto del programa, las tarjetas de la boletería y el JSON de Yelmo son los
reales del 22/9/2026, recortados a lo que usa el scraper.
"""
from datetime import date

from scraper import (CINES_MADRID, DORE_PROYECCIONES, _dore_arreglar_kerning,
                     _dore_combinar, _dore_programa, _dore_tarjetas,
                     _ideal_funciones)

assert CINES_MADRID == {"Cine Doré", "Cines Ideal"}

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

print("\nTodo OK")
