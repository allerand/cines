#!/usr/bin/env python3
"""
Test local del scraper de Club Lucero (clublucero.com), sin red:

    python3 test_lucero.py

Las entradas son las reales de la agenda de la portada de octubre y noviembre
de 2026. La sala estuvo en cero del 30/10 al 18/11/2026 porque no tenía
scraper: sólo había entrado a mano con el Bitbang.
"""
import json
from datetime import date

import scraper
from scraper import _lucero_agenda, _lucero_ciclo, _lucero_funciones


def f(iso, cycle, title, meta, link="entradas.html"):
    return _lucero_funciones({"iso": iso, "cycle": cycle, "title": title,
                              "meta": meta, "link": link})


# --- Una película ------------------------------------------------------------
[s] = f("2026-11-18", "Video Láser · Mes del Orgullo", "Happy Together",
        "21h · Wong Kar-wai, Hong Kong, 1997 · Filmada en Buenos Aires · "
        "Sala del primer piso · Gratis con reserva",
        "entradas.html?slug=happy-together")
assert (s.cine, s.title, s.fecha, s.hora) == ("Club Lucero", "Happy Together", "2026-11-18", "21:00")
assert (s.director, s.country, s.year) == ("Wong Kar-wai", "Hong Kong", 1997)
assert s.ciclo == "Video Láser"
assert s.ticket_url == "https://www.clublucero.com/entradas.html?slug=happy-together"
print("✓ una película: hora, director, país, año, ciclo y link a su entrada")

[s] = f("2026-11-27", "VHS ANIMÉ · Cine Club Lucero",
        "Inuyasha: El castillo de los sueños en el espejo",
        "19h · de Toshiya Shinohara, Japón, 2002 · Proyección en VHS · Presenta "
        "Hernán Panessi · Sala del primer piso · Con auriculares $7.000 / sin auriculares $5.000")
assert (s.director, s.country, s.year) == ("Toshiya Shinohara", "Japón", 2002)
assert s.ciclo == "VHS Animé"
print("✓ 'de Director, País, Año', y el ciclo gritado se baja sin tocar la sigla")

[s] = f("2026-10-31", "Especial Halloween · con Peliculero", "La virgen de la tosquera",
        "20h · de Laura Casabé, basada en cuentos de Mariana Enríquez · En el patio, "
        "bajo las enredaderas · Charla con el equipo después · $15.000")
assert (s.director, s.year, s.ciclo) == ("Laura Casabé", None, "Especial Halloween")
print("✓ sin año queda el director; la charla de después no la saca")

[s] = f("2026-11-11", "Pride de medianoche · Mes del Orgullo", "El lado oscuro de Oz",
        "23h · El mago de Oz + The Dark Side of the Moon · Sala del primer piso · Gratis con reserva")
assert (s.title, s.hora, s.director, s.year) == ("El lado oscuro de Oz", "23:00", "", None)
print("✓ sin ficha pasa si es en la sala, y no inventa un director")

[s] = f("2026-11-25", "Clásicos de culto queer · Mes del Orgullo",
        "¿Quién le teme a Virginia Woolf?",
        "21h · Mike Nichols, EE.UU., 1966 · Sala del primer piso · AGOTADO")
assert (s.title, s.country, s.year) == ("¿Quién le teme a Virginia Woolf?", "EE.UU.", 1966)
print("✓ una función agotada sigue siendo una función")

# --- Varias en una entrada ---------------------------------------------------
a, b = f("2026-11-19", "La ley del deseo · Mes del Orgullo",
         "Programa doble: Blow Job + Pink Narcissus",
         "21h · Andy Warhol + James Bidgood · +18 · Sala del primer piso · Gratis con reserva")
assert (a.title, a.director, a.hora) == ("Blow Job", "Andy Warhol", "21:00")
assert (b.title, b.director, b.hora) == ("Pink Narcissus", "James Bidgood", "21:00")
print("✓ el programa doble sale como dos funciones, cada una con su director")

a, b = f("2026-10-21", "Video Láser · Mes de los muertos", "Videodrome + Onibaba",
         "21h Videodrome (Cronenberg, 1983) · 23h Onibaba (Shindō, 1964) · Sala del primer piso · Gratis")
assert (a.title, a.hora, a.director, a.year) == ("Videodrome", "21:00", "Cronenberg", 1983)
assert (b.title, b.hora, b.director, b.year) == ("Onibaba", "23:00", "Shindō", 1964)
tres = f("2026-10-22", "Mes de los muertos", "Especial Stephen King",
         "19h Cementerio de animales · 21h Misery · 23h Carrie · Sala del primer piso · Gratis")
assert [(s.title, s.hora) for s in tres] == [
    ("Cementerio de animales", "19:00"), ("Misery", "21:00"), ("Carrie", "23:00")]
print("✓ una noche con varias películas: cada una con su hora, no el nombre de la noche")

[s] = f("2026-12-02", "Trasnoche", "Suspiria", "00h · Dario Argento, Italia, 1977 · Sala del primer piso")
assert (s.fecha, s.hora) == ("2026-12-03", "00:00")
print("✓ la trasnoche va al día siguiente")

# --- Lo que no es cine -------------------------------------------------------
assert f("2026-11-20", "Volate la peluca", "DJ Ian", "22 a 03h · Entrada libre",
         "ciclos.html#volate") == []
assert f("2026-11-21", "Noches de Sabaduki", "DJ Zoe", "22 a 03h · Patio · Entrada libre",
         "ciclos.html#sabaduki") == []
assert f("2026-11-04", "Curso × 6048 Comedia", "Impro Nivel 1",
         "18:30 a 21h · Un solo curso de 6 clases + muestra (21/10 al 25/11) · "
         "Sala del primer piso · Cupo 16 personas", "ciclos.html#impro") == []
assert f("2026-11-04", "Tras la niebla · Ciclo de charlas de cine", "Godzilla: las cuatro eras",
         "19 a 21h · 33 películas japonesas, más de 70 años de historia · Charla + preguntas · "
         "Sala del primer piso · Gratis con reserva",
         "entradas.html?slug=godzilla-las-cuatro-eras-tras-la-niebla") == []
# Aunque tuviera una hora sola, una charla en la sala no es una función.
assert f("2026-12-09", "Tras la niebla · Ciclo de charlas de cine", "Kaiju: los otros monstruos",
         "19h · Sala del primer piso · Gratis con reserva") == []
# Y un evento con hora sola que no es en la sala ni trae ficha, tampoco.
assert f("2026-12-10", "Noche de vinilos", "Selección de la casa", "21h · Patio · Entrada libre") == []
print("✓ los DJ, el curso de impro y las charlas quedan afuera")

assert f("2026-10-28", "Festival BITBANG · Día Internacional de la Animación",
         "Cortos de animación toda la noche",
         "19h Internacionales I · 20h II · 21h III · 22:15 Cortos verticales · 23h Cortos vergonzosos",
         "ciclos.html#bitbang") == []
print("✓ la noche de un festival no se parte en 'II' y 'III': se carga de su catálogo")

assert _lucero_ciclo("Pride de medianoche · Mes del Orgullo") == "Pride de medianoche"
assert _lucero_ciclo("Mes de los muertos") == "Mes de los muertos"
assert _lucero_ciclo("") == ""

# --- La portada --------------------------------------------------------------
agenda = [
    {"iso": "2026-11-12", "day": "Jue", "date": "12/11", "cycle": "La ley del deseo · Mes del Orgullo",
     "title": "Muerte en Venecia", "meta": "21h · Luchino Visconti, Italia, 1971 · Sala del primer piso · AGOTADO",
     "cta": "Agotado", "link": "entradas.html?slug=muerte-en-venecia"},
    {"iso": "2026-11-19", "day": "Jue", "date": "19/11", "cycle": "Trasnoche sáfica · Mes del Orgullo",
     "title": "Bound", "meta": "23h · Lana y Lilly Wachowski, EE.UU., 1996 · Sala del primer piso · Gratis con reserva",
     "cta": "Entradas", "link": "entradas.html?slug=bound"},
    {"iso": "2026-11-20", "day": "Vie", "date": "20/11", "cycle": "Volate la peluca", "title": "DJ Ian",
     "meta": "22 a 03h · Entrada libre", "cta": "Más info", "link": "ciclos.html#volate"},
    {"iso": "2026-11-26", "day": "Jue", "date": "26/11", "cycle": "La ley del deseo · Mes del Orgullo",
     "title": "Querelle", "meta": "21h · R. W. Fassbinder, Alemania, 1982 · Sala del primer piso · Gratis con reserva",
     "cta": "Entradas", "link": "entradas.html?slug=querelle"},
]
PORTADA = ('<!doctype html><html><body><div id="nights"></div><script type="module">'
           'import{createSubmission as e}from"./js/app.js";const a="",t='
           + json.dumps(agenda, ensure_ascii=False, separators=(",", ":"))
           + ',n=e=>String(e).replace(/[&<>"]/g,e=>({"&":"&amp;"}[e])),'
             'i=new Date(Date.now()-108e5).toISOString().slice(0,10);</script></body></html>')
assert _lucero_agenda(PORTADA) == agenda
assert _lucero_agenda("<html><body>En construcción</body></html>") is None
assert _lucero_agenda('<script>const t=[{"iso":"2026-11-19","title":</script>') is None
print("✓ la agenda sale del script de la portada; si no está o viene rota, None")


class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 18)


_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: PORTADA.encode("utf-8")
    r = scraper.scrape_lucero()
    assert [(s.title, s.fecha, s.hora) for s in r] == [
        ("Bound", "2026-11-19", "23:00"), ("Querelle", "2026-11-26", "21:00")], r
    assert "Club Lucero" not in scraper.FUENTES_CAIDAS
    print("✓ scrape_lucero: sólo lo que viene, sin los DJ ni lo que ya pasó")

    scraper.fetch_bytes = lambda url, *a, **k: b"<html><body>Sitio en mantenimiento</body></html>"
    assert scraper.scrape_lucero() == []
    assert "agenda" in scraper.FUENTES_CAIDAS.get("Club Lucero", "")
    print("✓ si la portada cambia, avisa a la auditoría en vez de dar un cero mudo")

    def _caida(url, *a, **k):
        raise TimeoutError("timed out")
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = _caida
    assert scraper.scrape_lucero() == []
    assert "no contestó" in scraper.FUENTES_CAIDAS.get("Club Lucero", "")
    print("✓ si el sitio no contesta, también")
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
