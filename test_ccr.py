#!/usr/bin/env python3
"""
Test del parseo de las páginas del Centro Cultural Recoleta, sin red.

    python3 test_ccr.py

Los fixtures son el HTML de las páginas reales, bajado el 8/10/2026, y pasan
por _ccr_lineas como en el scraper:

  · ccr_encuentro_europeo — la grilla en prosa del Encuentro de Cine Europeo:
    "Sáb. 03.10 | 16 h: “Long Good Thursday”, de Mika Kaurismäki (Finlandia)"
    y la sinopsis abajo. Tomando el renglón de arriba de cada fecha como
    título, la historia del 4/10 publicó "matthias dirige una exitosa agencia
    de alquiler de amigos…" (la sinopsis de la función ANTERIOR); y el primer
    arreglo, que buscaba el título debajo de la fecha, no encontraba ninguno
    y tiraba las 16 funciones. Trae además "Dom 11.10" sin punto, dos fechas
    en una línea, un "de" sin coma, dos directores con un solo apellido,
    cuatro países y el título en <strong>.
  · ccr_sabados_superaccion — un ciclo con "Actividades" que linkean a cada
    película, con todas las funciones del año. Las de enero ("Sáb. 10.01") no
    pueden volver como si fueran de enero de 2027.
  · ccr_comedias_de_terror — un ciclo cuyas "Actividades" no linkean (el
    título va en <strong>), pero cada película tiene su página con el título
    como slug. "Vie. 02.10 y 30.10": la segunda fecha sin día de la semana, y
    El joven Frankenstein del 30/10 no salía. Debajo del nombre del ciclo dice
    "Viernes de octubre | 18 h", que no es una película.
  · ccr_buscando_a_shakespeare — "Jueves de octubre | 18 h" sin una sola
    fecha: nunca entró a la cartelera. Entradas BA vende los cuatro jueves.
  · ccr_<película> — la página de cada película, con la ficha al final:
    "Prínicipe Valiente, dirigida por Henry Hathaway. EE.UU., 1954. …". Sin
    director ni año, el enrichment no se animaba a elegir entre homónimos.
"""
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

import scraper
from scraper import (CCR_BASE, CCR_INDEX, _ccr_actividades, _ccr_fichas, _ccr_lineas,
                     _ccr_parse_lineas, scrape_ccr)

FIX = Path(__file__).parent / "tests" / "fixtures"
URL = "http://centroculturalrecoleta.org/agenda/encuentro-de-cine-europeo"


def sopa(nombre):
    return BeautifulSoup((FIX / nombre).read_text(encoding="utf-8"), "html.parser")


def funciones(nombre, hoy):
    return [(s.fecha, s.hora, s.title, s.director, s.country)
            for s in _ccr_parse_lineas(_ccr_lineas(sopa(nombre)), URL, hoy)]


# Lo que contesta el sitio a cada URL que pide scrape_ccr. Lo que no está acá
# es un 404.
PAGINAS = {
    CCR_INDEX: "ccr_agenda_cine.html",
    CCR_BASE + "/agenda/encuentro-de-cine-europeo": "ccr_encuentro_europeo.html",
    CCR_BASE + "/agenda/ciclos/comedias-de-terror": "ccr_comedias_de_terror.html",
    CCR_BASE + "/agenda/pelicula-sorpresa": "ccr_pelicula_sorpresa.html",
    CCR_BASE + "/agenda/buscando-a-shakespeare": "ccr_buscando_a_shakespeare.html",
    CCR_BASE + "/agenda/ciclos/sabados-de-superaccion": "ccr_sabados_superaccion.html",
    CCR_BASE + "/agenda/la-tiendita-del-horror": "ccr_la_tiendita_del_horror.html",
    CCR_BASE + "/agenda/el-joven-frankenstein": "ccr_el_joven_frankenstein.html",
    CCR_BASE + "/agenda/la-hora-del-espanto": "ccr_la_hora_del_espanto.html",
    CCR_BASE + "/agenda/el-club-del-terror": "ccr_el_club_del_terror.html",
    CCR_BASE + "/agenda/prinicipe-valiente": "ccr_prinicipe_valiente.html",
}


def fetch_fixture(url):
    if url not in PAGINAS:
        raise OSError(f"404 {url}")
    return sopa(PAGINAS[url])


def main():
    fallas = []

    def check(nombre, got, want):
        if got != want:
            fallas.append(f"{nombre}:\n  esperado {want}\n  obtenido {got}")

    enc = funciones("ccr_encuentro_europeo.html", date(2026, 10, 3))
    check("encuentro: la grilla entera", [(f, h, t) for f, h, t, _, _ in enc], [
        ("2026-10-03", "16:00", "Long Good Thursday"),
        ("2026-10-03", "18:00", "Peacock"),
        ("2026-10-04", "16:00", "Cara o seca"),
        ("2026-10-04", "18:00", "La Gioia"),
        ("2026-10-10", "18:00", "Smaragda"),
        ("2026-10-11", "16:00", "Gente oculta"),
        ("2026-10-11", "18:00", "Misterioso asesinato en la montaña"),
        ("2026-10-17", "18:00", "Siete días"),
        ("2026-10-25", "18:00", "Siete días"),
        ("2026-10-18", "18:00", "Voces de libertad"),
        ("2026-11-01", "18:00", "Voces de libertad"),
        ("2026-10-24", "18:00", "No hay fantasmas en la calle Dobra"),
        ("2026-10-25", "16:00", "Jippie No More!"),
        ("2026-10-31", "16:00", "La memoria del perfume de las cosas"),
        ("2026-10-31", "18:00", "Dražen"),
        ("2026-11-01", "16:00", "Songs of Slow Burning Earth"),
    ])
    ficha = {t: (d, c) for _, _, t, d, c in enc}
    check("encuentro: director y país", [ficha.get(t) for t in (
        "Long Good Thursday", "Cara o seca", "La memoria del perfume de las cosas",
        "Dražen", "Songs of Slow Burning Earth")], [
        ("Mika Kaurismäki", "Finlandia"),
        ("Lenny Guit, Harpo Guit", "Bélgica"),
        ("António Fonseca", "Portugal"),
        ("Danilo Serbedzija, Ljubo Zdjelarevic", "Croacia"),
        ("Olha Zhurba", "Ucrania, Dinamarca, Francia, Suecia"),
    ])
    check("encuentro: ninguna sinopsis como título",
          [t for _, _, t, _, _ in enc if len(t.split()) > 8], [])

    check("superacción: sólo lo que viene",
          [(f, h, t) for f, h, t, _, _ in funciones("ccr_sabados_superaccion.html", date(2026, 10, 8))],
          [("2026-10-10", "16:00", "Prínicipe Valiente")])
    # En diciembre la ventana de 90 días ya llega a marzo de 2027; los
    # sábados 10.01, 14.02 y 14.03 son de 2026 (en 2027 caen domingo) y no
    # tienen que aparecer.
    check("superacción: enero no vuelve en 2027",
          funciones("ccr_sabados_superaccion.html", date(2026, 12, 20)), [])

    check("comedias: cada película con su fecha, y el ciclo no es una",
          [(f, h, t) for f, h, t, _, _ in funciones("ccr_comedias_de_terror.html", date(2026, 10, 8))], [
        ("2026-10-23", "18:00", "La tiendita del horror"),
        ("2026-10-30", "18:00", "El joven Frankenstein"),
        ("2026-10-09", "18:00", "La hora del espanto"),
        ("2026-10-16", "18:00", "El club del terror"),
    ])
    check("comedias: 'Vie. 02.10 y 30.10' son dos funciones",
          [f for f, _, t, _, _ in funciones("ccr_comedias_de_terror.html", date(2026, 10, 1))
           if t == "El joven Frankenstein"],
          ["2026-10-02", "2026-10-30"])

    check("shakespeare: 'Jueves de octubre' son los jueves que quedan",
          funciones("ccr_buscando_a_shakespeare.html", date(2026, 10, 8)), [
        (f"2026-10-{d:02d}", "18:00", "Buscando a Shakespeare", "Gustavo Garzón", "Argentina")
        for d in (8, 15, 22, 29)
    ])
    check("shakespeare: el año sale de la ficha",
          {s.year for s in _ccr_parse_lineas(_ccr_lineas(sopa("ccr_buscando_a_shakespeare.html")),
                                             URL, date(2026, 10, 8))}, {2025})

    check("actividades: links, y el slug del título si no hay link",
          [_ccr_actividades(sopa("ccr_comedias_de_terror.html")),
           _ccr_actividades(sopa("ccr_sabados_superaccion.html"))[-2:]], [
        [("La tiendita del horror", CCR_BASE + "/agenda/la-tiendita-del-horror"),
         ("El joven Frankenstein", CCR_BASE + "/agenda/el-joven-frankenstein"),
         ("La hora del espanto", CCR_BASE + "/agenda/la-hora-del-espanto"),
         ("El club del terror", CCR_BASE + "/agenda/el-club-del-terror")],
        [("Furia de titanes", CCR_BASE + "/agenda/furia-de-titanes"),
         ("Prínicipe Valiente", CCR_BASE + "/agenda/prinicipe-valiente")],
    ])

    check("ficha: título, director, país y año", [
        _ccr_fichas(_ccr_lineas(sopa("ccr_prinicipe_valiente.html"))),
        # Sin coma antes de "dirigida", el título en <em>, cinco directores y
        # dos países con barra.
        _ccr_fichas(_ccr_lineas(sopa("ccr_casino_royale.html"))),
    ], [
        {"prinicipe valiente": {"director": "Henry Hathaway", "country": "EE.UU.",
                                "year": 1954}},
        {"casino royale": {"director": "John Huston, Robert Parrish, Val Guest, "
                                       "Ken Hughes, Joseph McGrath",
                           "country": "EE.UU., Gran Bretaña", "year": 1967}},
    ])

    # De punta a punta: el índice, cada evento y la página de cada película
    # de los ciclos.
    fetch_real = scraper.fetch_html
    scraper.fetch_html = fetch_fixture
    try:
        todo = scrape_ccr(date(2026, 10, 8))
    finally:
        scraper.fetch_html = fetch_real
    check("scrape_ccr: los ciclos con la ficha de cada película", [
        (s.fecha, s.title, s.director, s.country, s.year)
        for s in todo if "/ciclos/" in s.ticket_url], [
        ("2026-10-23", "La tiendita del horror", "Frank Oz", "EE.UU.", 1986),
        ("2026-10-30", "El joven Frankenstein", "Mel Brooks", "EE.UU.", 1974),
        ("2026-10-09", "La hora del espanto", "Tom Holland", "EE.UU.", 1985),
        ("2026-10-16", "El club del terror", "Richard Wenk", "EE.UU.", 1986),
        ("2026-10-10", "Prínicipe Valiente", "Henry Hathaway", "EE.UU.", 1954),
    ])
    check("scrape_ccr: cuántas por página", sorted(
        (u.rsplit("/", 1)[-1], sum(1 for s in todo if s.ticket_url == u))
        for u in {s.ticket_url for s in todo}), [
        ("buscando-a-shakespeare", 4),
        ("comedias-de-terror", 4),
        ("encuentro-de-cine-europeo", 12),
        ("pelicula-sorpresa", 1),
        ("sabados-de-superaccion", 1),
    ])
    # La duración de la ficha es un redondeo (90' para La hora del espanto,
    # que dura 107): como dato del cine, el enrichment descartaba la correcta.
    check("scrape_ccr: sin la duración del sitio",
          [s.title for s in todo if s.duration], [])

    html = ("<p>Sáb. 03.10 | 16 h: <strong>“Long Good Thursday”</strong>, de "
            "<em>Mika Kaurismäki</em> (Finlandia)<br>Mientras hace las compras…</p>")
    check("html: las negritas no parten la línea de la fecha",
          _ccr_lineas(BeautifulSoup(html, "html.parser"))[0],
          "Sáb. 03.10 | 16 h: “Long Good Thursday”, de Mika Kaurismäki (Finlandia)")

    comedias = """
Comedias de terror
Viernes de octubre | 18 h
Cine | La hora del espanto
Vie. 09.10 | 18 h | Cine
Cine | El club del terror
Vie. 16.10 y Vie. 23.10 | 18 h | Cine
Taller | Maquillaje de monstruos
Sáb. 17.10 | 15 h | Taller
Música | Banda de sonido
Sáb. 17.10 | 20 h
Horarios
Vie. 09.10 | 18 h | Cine
"""
    check("ciclo con categoría en el título: sólo cine",
          [(s.fecha, s.hora, s.title) for s in
           _ccr_parse_lineas(comedias.splitlines(), URL, date(2026, 10, 8))], [
        ("2026-10-09", "18:00", "La hora del espanto"),
        ("2026-10-16", "18:00", "El club del terror"),
        ("2026-10-23", "18:00", "El club del terror"),
    ])

    if fallas:
        print("\n".join(fallas))
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
