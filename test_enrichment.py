#!/usr/bin/env python3
"""
Test local del enrichment de Letterboxd, sin red: cada caso es un match
equivocado que llegó a publicarse.

    python3 test_enrichment.py

Casi todos son el mismo error. La función llega sin director ni año —Lorca,
Multiplex, los comerciales, Cacodelphia cuando no se puede leer la ficha—, el
enrichment le pregunta el título a los buscadores y se queda con lo primero que
pasa el filtro: otra película que se llama parecido, o un homónimo.
"""
import asyncio
import tempfile
from pathlib import Path

import letterboxd as lb
from letterboxd import _decidir_sin_hints, _name_overlap, _validate_meta, clase_titulo


def film(title, year, duration=None, director="", titulos=None):
    return {"url": f"https://letterboxd.com/film/{lb.slugify(title)}-{year}/",
            "title_en": title, "year": year, "duration": duration,
            "director": director, "country": "", "genre": "",
            "titulos": titulos or [title]}


# --- Títulos ----------------------------------------------------------------
assert clase_titulo(["OLD BOY"], ["Oldboy", "Old Boy", "Oldboy: Cinco días para vengarse"]) == "exacto"
assert clase_titulo(["Oldboy"], ["Oldboy: Cinco días para vengarse"]) == "exacto"
assert clase_titulo(["Romeo & Ofelia"], ["Romeo y Ofelia"]) == "exacto"
assert clase_titulo(["TERMINATOR 2 - EL JUICIO FINAL"], ["Terminator 2: Judgment Day"]) == "exacto"
assert clase_titulo(["Moonrise"], ["Moonrise (Noche sin luna)"]) == "exacto"
print("✓ títulos: alternativos, subtítulos y '&' cuentan como el mismo título")

assert clase_titulo(["OLD BOY"], ["Old Suffolk Boy"]) == "pisado"
assert clase_titulo(["Tu rostro"], ["Tengo miedo de olvidar tu rostro"]) == "pisado"
assert clase_titulo(["Sin sol"], ["No hay sábado sin sol"]) == "pisado"
assert clase_titulo(["Vértigo"], ["Fall 2: Deadpoint", "Vértigo 2: Punto muerto"]) == "pisado"
print("✓ títulos: otra película que agrega palabras es 'pisado' (Old Suffolk Boy, Vértigo 2)")

assert clase_titulo(["El gran falsificador"], ["The Money Maker", "L'Affaire Bojarski"]) == "distinto"
assert clase_titulo(["Old Boy"], ["Old Boyfriends"]) == "distinto"
# Un título largo que el cine cortó no es "pisado": la película empieza igual.
assert clase_titulo(["Tadeo el explorador y la lámpara"],
                    ["Tadeo el explorador y la lámpara maravillosa"]) == "distinto"
print("✓ títulos: una traducción o un título cortado no se confunden con 'pisado'")

# --- Directores -------------------------------------------------------------
assert not _name_overlap("Joaquín Pereyra", "Joaquín Farías Caamaño")
print("✓ director: compartir el nombre de pila ya no alcanza (Milonga para tres)")
assert _name_overlap("David Frenkel", "David Frankel")
assert _name_overlap("Ezequiel Enriquez Mena", "Ezequiel Erriquez")
assert _name_overlap("Anxos Fanzas", "Anxos Fazáns")
print("✓ director: un apellido mal tipeado por la fuente sigue coincidiendo")
assert _name_overlap("Park Chan-wook", "Chan-wook Park")
assert _name_overlap("Peter Spierig", "Michael Spierig, Peter Spierig")
assert _name_overlap("Jean-Pierre Dardenne y Luc Dardenne", "Luc Dardenne")
assert _name_overlap("Hitchcock", "Alfred Hitchcock")
print("✓ director: orden coreano, codirecciones y apellido solo")

# --- Validación con hints ---------------------------------------------------
suffolk = {"title_en": "Old Suffolk Boy", "year": None, "duration": 135, "director": "Louis Holder"}
assert not _validate_meta(suffolk, None, "", None)
assert not _validate_meta(suffolk, None, "", None, "pisado")
print("✓ validación: sin hints, una ficha sin año no pasa (Old Suffolk Boy)")
# Con un director que confirme, el título traducido no importa (ciclo Borzage).
assert _validate_meta({"year": 1939, "director": "Frank Borzage"}, 1939, "Frank Borzage", None, "distinto")
# Con año solo, un título pisado sigue siendo otra película.
assert not _validate_meta({"year": 2026, "director": "M. Spierig"}, 2026, "", None, "pisado")
print("✓ validación: con director el título no se mira; con año solo, 'pisado' no pasa")

# --- Decidir sin hints ------------------------------------------------------
oldboy = film("Oldboy", 2003, 120, "Park Chan-wook",
              ["Oldboy", "Old Boy", "Oldboy: Cinco días para vengarse"])
oldboy_2018 = film("Old Boy", 2018, 14)
old_suffolk = film("Old Suffolk Boy", None, 135, "Louis Holder")
reluctant = film("Reluctant Bachelor", 2011, 58)   # es lo que hay en /film/old-boy/
cands = [(reluctant, "slug"), (old_suffolk, "busqueda"), (oldboy_2018, "imdb"), (oldboy, "imdb")]

elegido, motivo = _decidir_sin_hints(["OLD BOY"], 119, cands)
assert elegido is oldboy, (elegido, motivo)
print(f"✓ Old Boy de 119 min → Oldboy (2003), aunque sea vieja: {motivo}")
elegido, motivo = _decidir_sin_hints(["OLD BOY"], None, [(reluctant, "slug"), (old_suffolk, "busqueda"),
                                                          (film("Old Boy", 2018), "imdb"), (oldboy, "imdb")])
assert elegido is None, elegido
print(f"✓ Old Boy sin duración → sin ficha, no Old Suffolk Boy: {motivo}")

spider = film("Spider Island", 2026, 95)
islandias = [film("Islandia", 2025, 94), film("Islandia", 2023, 80), film("Islandia", 2018)]
elegido, motivo = _decidir_sin_hints(["ISLANDIA"], 94, [(spider, "imdb")] + [(i, "imdb") for i in islandias])
assert elegido is islandias[0], (elegido, motivo)
print("✓ Islandia de 94 min → el documental de 2025, no Spider Island (95 min)")
elegido, _ = _decidir_sin_hints(["ISLANDIA"], None, [(spider, "imdb")] + [(i, "imdb") for i in islandias])
assert elegido is islandias[0], elegido
print("✓ Islandia sin duración → la de 2025: de las tres que se llaman así, es el estreno")
# Lo que pasa de verdad: el documental no está en Letterboxd, las 'Islandia'
# que sí están duran otra cosa, y queda Spider Island con 95 minutos.
reales = [film("Islandia", 2023, 77), film("Islandia", 2018, 18)]
elegido, motivo = _decidir_sin_hints(["ISLANDIA"], 94, [(spider, "imdb")] + [(i, "imdb") for i in reales])
assert elegido is None, (elegido, motivo)
elegido, _ = _decidir_sin_hints(["ISLANDIA"], 94, [(spider, "imdb")], homonimo_fuera=True)
assert elegido is None
print(f"✓ Islandia fuera de Letterboxd → sin ficha, no Spider Island: {motivo}")

vertigo = [film("Fall 2: Deadpoint", 2026, 98, "Michael Spierig", ["Fall 2: Deadpoint", "Vértigo 2: Punto muerto"]),
           film("Vertigo", 1958, 128, "Alfred Hitchcock", ["Vertigo", "Vértigo", "De entre los muertos"]),
           film("Vertigo", 2019), film("Fall", 2022, 107, titulos=["Fall", "Vértigo"])]
elegido, motivo = _decidir_sin_hints(["Vértigo"], None, [(v, "imdb") for v in vertigo])
assert elegido is None, elegido
print(f"✓ Vértigo (CCR, ciclo Hitchcock) → sin ficha, no Fall 2: {motivo}")

odisea = [film("The Odyssey", 1997, 176, titulos=["The Odyssey", "La Odisea"]),
          film("The Odyssey", 2026, 175, "Christopher Nolan", ["The Odyssey", "La Odisea"])]
elegido, motivo = _decidir_sin_hints(["La Odisea"], None, [(o, "imdb") for o in odisea])
assert elegido is odisea[1], elegido
invitacion = [film("The Invite", 2026, 107, "Olivia Wilde", ["The Invite", "La invitación"]),
              film("The Invitation", 2022, 105, titulos=["The Invitation", "La invitación"])]
elegido, _ = _decidir_sin_hints(["LA INVITACIÓN"], 107, [(i, "imdb") for i in invitacion])
assert elegido is invitacion[0], elegido
print(f"✓ La Odisea (Multiplex) → la de Nolan y no la miniserie de 1997: {motivo}")
codigo = [film("Tin Soldier", 2025, titulos=["Tin Soldier", "Código: Venganza"]),
          film("Mutiny", 2026, titulos=["Mutiny", "Código: Venganza"])]
elegido, _ = _decidir_sin_hints(["Codigo: Venganza"], None, [(c, "imdb") for c in codigo])
assert elegido is codigo[1], elegido
elegido, _ = _decidir_sin_hints(["Codigo: Venganza"], None,
                                [(c, "imdb") for c in codigo + [film("Otra", 2026, titulos=["Código: Venganza"])]])
assert elegido is None, elegido
print("✓ Código: Venganza → Mutiny (2026), la más nueva; si dos del mismo año empatan, sin ficha")
assert clase_titulo(["Spider-man: Un Dia Nuevo"], ["Spider-Man"]) == "distinto"
assert clase_titulo(["Zona Cero - Colony"], ["Colony", "Zona Cero"]) == "exacto"
assert clase_titulo(["Backrooms - Versión extendida"], ["Backrooms"]) == "exacto"
print("✓ el título del cine no se corta en ':' — 'Spider-Man: Un día nuevo' no es 'Spider-Man'")

frida = [film("Frida, Still Life", 1983, 108, "Paul Leduc", ["Frida, Still Life", "Frida, naturaleza viva"]),
         film("Naturaleza Viva", 2020), film("Natura Bizia", 2021)]
elegido, _ = _decidir_sin_hints(["Frida, naturaleza viva"], None, [(f, "imdb") for f in frida])
assert elegido is None
print("✓ Frida, naturaleza viva → sin ficha, no Natura Bizia (2021)")

tu_rostro = film("Tengo miedo de olvidar tu rostro", 2025, 12)
elegido, _ = _decidir_sin_hints(["TU ROSTRO"], None, [(tu_rostro, "imdb")])
assert elegido is None
print("✓ Tu rostro → no 'Tengo miedo de olvidar tu rostro'")

mm = film("The Money Maker", 2025, 110, "Jean-Paul Salomé", ["The Money Maker", "L'Affaire Bojarski"])
elegido, motivo = _decidir_sin_hints(["El gran falsificador"], None,
                                     [(mm, "imdb"), (film("The Big Fake", 2025), "imdb"), (film("The Forger", 2012), "imdb")])
assert elegido is mm, elegido
print(f"✓ El gran falsificador (Lorca) → The Money Maker, como hasta ahora: {motivo}")
# Pero un título distinto que sale de adivinar el slug no es una traducción.
elegido, _ = _decidir_sin_hints(["OLD BOY"], None, [(film("Reluctant Bachelor", 2026), "slug")])
assert elegido is None
print("✓ un slug que lleva a otra película no cuenta como traducción")

# --- TMDb: una sola película por ficha --------------------------------------
lb._tmdb_credential = lambda: ("v3", "x")
lb.tmdb_search_movie = lambda q, y=None: [{"id": 1, "year": 2003}, {"id": 2, "year": 2003}, {"id": 3, "year": 2003}]
TMDB = {
    1: {"year": 2003, "title_en": "Oldboy", "titulos": ["Oldboy"]},                      # sin director
    2: {"year": 2003, "director": "Park Chan-wook", "country": "", "titulos": ["Oldboy"]},
    3: {"year": 2003, "director": "Park Chan-wook", "country": "South Korea", "title_es": "Otra película"},
}
lb.fetch_tmdb_movie_meta = lambda mid: dict(TMDB[mid])
out = lb.fill_meta_from_tmdb(dict(oldboy, country="", titulos=None), "OLD BOY", None, "", "")
assert out.get("title_es") != "Otra película" and not out.get("country"), out
print("✓ TMDb completa desde UNA película: no mezcla el país o el título de otra")

lb.tmdb_search_movie = lambda q, y=None: [{"id": 4, "year": 1920}]
lb.fetch_tmdb_movie_meta = lambda mid: {"year": 1920, "director": "Jerome Storm", "duration": 60,
                                        "title_en": "An Old Fashioned Boy", "titulos": ["An Old Fashioned Boy"]}
out = lb.fill_meta_from_tmdb(lb._empty_meta("OLD BOY"), "OLD BOY", None, "", "")
assert not out.get("director"), out
print("✓ TMDb sin hints no agarra 'An Old Fashioned Boy' (1920) por Old Boy")

# --- El camino completo, con caché ------------------------------------------
lb._tmdb_credential = lambda: ("", "")
PAGINAS = {f["url"]: f for f in (oldboy, oldboy_2018, reluctant, old_suffolk)}
lb.fetch_film_page = lambda u: u if u in PAGINAS else None
lb.parse_film_soup = lambda s, u: dict(PAGINAS[u], titulos=list(PAGINAS[u]["titulos"]))
lb.imdb_suggest = lambda q: [{"tt": "tt1", "title": "Old Boy", "year": 2018},
                             {"tt": "tt2", "title": "Oldboy", "year": 2003}]
lb.letterboxd_url_from_imdb = lambda tt: {"tt1": oldboy_2018["url"], "tt2": oldboy["url"]}[tt]


class PaginaFalsa:
    async def goto(self, *a, **k): pass
    async def wait_for_timeout(self, ms): pass
    async def content(self): return "<html></html>"


with tempfile.TemporaryDirectory() as d:
    cache = lb.LetterboxdCache(Path(d) / "cache.json")
    meta = asyncio.run(lb.enrich_title("OLD BOY", PaginaFalsa(), cache, delay=0))
    assert not meta["url"] and "OLD BOY" in lb.SIN_FICHA, meta
    assert cache.get("OLD BOY").get("sin_ficha")
    print(f"✓ camino completo sin duración: sin ficha, y queda anotado ({lb.SIN_FICHA['OLD BOY']})")

    # Al día siguiente la ficha de Cacodelphia se pudo leer y trae la duración:
    # no se espera a que venza la decisión anterior.
    meta = asyncio.run(lb.enrich_title("OLD BOY", PaginaFalsa(), cache, delay=0, hint_duration=119))
    assert meta["url"] == oldboy["url"] and meta["year"] == 2003, meta
    assert "titulos" not in cache.get("OLD BOY"), "los alternativos no van al caché"
    print("✓ con la duración que faltaba: Oldboy (2003), sin esperar tres días")

    # Y queda: una corrida sin duración no la tira.
    lb.imdb_suggest = lambda q: (_ for _ in ()).throw(AssertionError("no debería buscar"))
    meta = asyncio.run(lb.enrich_title("OLD BOY", PaginaFalsa(), cache, delay=0))
    assert meta["url"] == oldboy["url"], meta
    print("✓ la elección queda en el caché aunque la próxima corrida venga sin duración")

print("\nTodo OK")
