#!/usr/bin/env python3
"""
Test de la agenda del MALBA contra las programaciones de sus ciclos, sin red:

    python3 test_malba_agenda.py

El ciclo El Romerazo iba a seguir el 22, 23, 29 y 30 de octubre de 2026. A
principios de mes el MALBA le dio esos días al festival Asterisco y cortó la
Programación del ciclo el 16/10, pero dejó en la agenda día por día las
películas del Romerazo de esos días, con sus páginas. La web publicó Elvira
Fernández, vendedora de tienda el jueves 22 a las 23, entre dos funciones del
festival en la misma sala, y el MALBA no la daba.

Las páginas de acá son las del museo recortadas a lo que lee el scraper.
"""
import urllib.error
from datetime import date

from bs4 import BeautifulSoup

import scraper

BASE = "https://malba.org.ar"
CICLO = f"{BASE}/evento/el-romerazo/"
FESTIVAL = f"{BASE}/evento/asterisco-festival-internacional-de-cine-lgbtiq-2/"


def programacion(h1, etiqueta, dias):
    parrafos = "".join(f'<p>{dia}<br/>' + "<br/>".join(funciones) + "</p>" for dia, funciones in dias)
    return (f"<p>Cine</p><p>{etiqueta}</p><h1>{h1}</h1><p>Auditorio</p>"
            f"<h3>Programación</h3>{parrafos}<p>Comprar entradas</p>")


def pelicula(titulo, etiqueta, dia):
    return (f"<p>Cine</p><p>{etiqueta}</p><h1>{titulo}</h1>"
            f"<p>De Manuel Romero</p><p>{dia}</p><p>Auditorio</p>")


def tarjetas(*funciones):
    return "".join(
        f'<div><span class="elementor-post-info__item--type-custom"> {hora} Cine </span>'
        f'<div class="elementor-page-title"><p><a href="{BASE}/evento/{slug}/">{titulo}</a></p></div></div>'
        for hora, titulo, slug in funciones)


WEB = {
    f"{BASE}/cine/": f'<a href="{CICLO}">El Romerazo</a><a href="{FESTIVAL}">Asterisco</a>',
    # La Programación del ciclo, ya recortada al 16/10.
    CICLO: programacion("El Romerazo", "Ciclo", [
        ("JUEVES 15", ["19:00 La vida es un tango, de Manuel Romero"]),
        ("VIERNES 16", ["23:00 Ven… mi corazón te llama, de Manuel Romero"]),
    ]),
    FESTIVAL: programacion("Asterisco Festival Internacional de Cine LGBTIQ+", "Ciclo", [
        ("JUEVES 22", ["18:00 Tristán y los días por venir, de Martina Matkzin y Gabriela Uassouf",
                       "20:00 Vorágine, de Daniela Escolar y Paula Monesterolo",
                       "22:00 Siemprevivas, de Mar López Zapata",
                       "24:00 Las hijas del fuego, de Albertina Carri"]),
        ("JUEVES 29", ["22:00 Retrospectiva Rafael Maino"]),
    ]),
    # La agenda todavía lista las del Romerazo entre las del festival.
    f"{BASE}/agenda/on/2026/10/22/": tarjetas(
        ("18:00", "Tristán y los días por venir", "tristan-y-los-dias-por-venir"),
        ("19:00", "El diablo andaba en los choclos", "el-diablo-andaba-en-los-choclos"),
        ("20:00", "Vorágine", "voragine"),
        ("21:00", "Mujeres que bailan", "mujeres-que-bailan"),
        ("23:00", "Elvira Fernández, vendedora de tienda", "elvira-fernandez-vendedora-de-tienda")),
    f"{BASE}/agenda/on/2026/10/23/": tarjetas(("20:00", "Annemarie", "annemarie")),
    # El festival escribe "Retrospectiva Rafael Maino"; la agenda, "RAM".
    f"{BASE}/agenda/on/2026/10/29/": tarjetas(
        ("22:00", "Retrospectiva RAM", "retrospectiva-rafael-maino")),
    # Una del festival que su Programación no nombra: el festival sigue, así
    # que no hay cómo saber quién tiene razón y se deja.
    f"{BASE}/agenda/on/2026/10/30/": tarjetas(("20:00", "Función sorpresa", "funcion-sorpresa")),
    f"{BASE}/evento/funcion-sorpresa/": pelicula(
        "Función sorpresa", "Asterisco Festival Internacional de Cine LGBTIQ+",
        "Viernes 30 de octubre a las 20:00"),
    f"{BASE}/evento/el-diablo-andaba-en-los-choclos/": pelicula(
        "El diablo andaba en los choclos", "Ciclo El Romerazo", "Jueves 22 de octubre a las 19:00"),
    f"{BASE}/evento/elvira-fernandez-vendedora-de-tienda/": pelicula(
        "Elvira Fernández, vendedora de tienda", "Ciclo El Romerazo", "Jueves 22 de octubre a las 23:00"),
    f"{BASE}/evento/retrospectiva-rafael-maino/": pelicula(
        "Retrospectiva RAM", "Asterisco Festival Internacional de Cine LGBTIQ+",
        "Jueves 29 de octubre a las 22:00"),
    f"{BASE}/evento/annemarie/": pelicula(
        "Annemarie", "Estreno", "Viernes 23 de octubre a las 20:00"),
}
# Ésta ya la borró el museo.
BORRADAS = {f"{BASE}/evento/mujeres-que-bailan/"}


def fetch_html(url):
    url = url.rstrip("/") + "/"     # los ciclos se piden sin la barra final
    if url in BORRADAS:
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    return BeautifulSoup(WEB.get(url, "<html></html>"), "html.parser")


original = scraper.fetch_html
scraper.fetch_html = fetch_html
try:
    funciones = scraper.scrape_malba(2, hoy=date(2026, 10, 21))
finally:
    scraper.fetch_html = original
print()

por_slot = {(s.fecha, s.hora): s for s in funciones}
assert sorted(por_slot) == [
    ("2026-10-22", "18:00"), ("2026-10-22", "20:00"), ("2026-10-22", "22:00"),
    ("2026-10-22", "24:00"), ("2026-10-23", "20:00"), ("2026-10-29", "22:00"),
    ("2026-10-30", "20:00"),
], sorted((s.fecha, s.hora, s.title) for s in funciones)
assert all("Asterisco" in s.ciclo for s in funciones if s.fecha in ("2026-10-22", "2026-10-29"))
print("✓ el jueves 22 quedan las cuatro del festival y ninguna del Romerazo")

titulos = {s.title for s in funciones}
assert not titulos & {"El diablo andaba en los choclos", "Elvira Fernández, vendedora de tienda"}
print("✓ una película de un ciclo cuya Programación ya terminó no se publica")
assert "Mujeres que bailan" not in titulos
print("✓ una función cuya página borró el museo no se publica")

assert por_slot[("2026-10-29", "22:00")].title == "Retrospectiva Rafael Maino"
assert "Retrospectiva RAM" not in titulos
print("✓ la misma función con otro título en la agenda no se duplica")

assert por_slot[("2026-10-23", "20:00")].title == "Annemarie"
print("✓ un estreno suelto, que no es de ningún ciclo, sigue saliendo de la agenda")

assert por_slot[("2026-10-30", "20:00")].title == "Función sorpresa"
print("✓ lo que la agenda suma a un ciclo que sigue no se saca: no hay cómo saber quién tiene razón")

assert scraper._malba_fecha_cercana(3, 1, date(2026, 10, 21)) == date(2026, 10, 1)
assert scraper._malba_fecha_cercana(3, 22, date(2026, 10, 21)) == date(2026, 10, 22)
print("✓ 'JUEVES 1' es el 1/10 que pasó; 'JUEVES 22', el de mañana")

print("\nTodo OK")
