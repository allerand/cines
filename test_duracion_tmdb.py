#!/usr/bin/env python3
"""
Test del filtro por duración en el último paso del enrichment, sin red.

    python3 test_duracion_tmdb.py

El 9/9/2026 un lector avisó por mail que "Old Boy" del viernes 11 y el martes
15 en Cacodelphia figuraba en la cartelera como "una comedia yanki de 1920".
Era cierto. La ficha de Cacodelphia no publica director ni año —los infiere
_cacodelphia_trailer_meta del título del trailer de YouTube, y ese trailer no
matcheaba el formato esperado—, así que enrich_title llegaba a su último paso
sin un solo dato con qué validar y se quedaba con el primer resultado que TMDb
devuelve para "OLD BOY": "An Old Fashioned Boy" (Jerome Storm, 1920, 50
minutos), que en TMDb se titula exactamente "Old Boy". El Oldboy de Park
Chan-wook, que ahí es una sola palabra, quedaba más abajo.

Lo que Cacodelphia SÍ publica es la duración: 119 minutos. El dato ya viajaba
hasta enrich_title y ya se usaba para validar los matches de Letterboxd
(_validate_meta), pero fill_meta_from_tmdb —el paso que corre cuando Letterboxd
no encontró nada, que el 10/9/2026 eran 56 de los 307 títulos de la cartelera—
ni lo recibía.

La tolerancia es ancha (_TMDB_DUR_TOL) a propósito: los cines redondean y
anuncian el bloque con trailers. En la cartelera del 10/9/2026 la diferencia
legítima más grande era de 20 minutos y los matches equivocados se pasaban por
más de 60.
"""
import letterboxd
from letterboxd import _empty_meta, _TMDB_DUR_TOL, fill_meta_from_tmdb

# Catálogo de mentira: cada película con su fila de /search/movie y su ficha de
# /movie/{id}, que es lo único que fill_meta_from_tmdb le pide a TMDb.
CATALOGO = {
    1: {"search": {"id": 1, "title": "Old Boy",
                   "original_title": "An Old Fashioned Boy", "year": 1920},
        "meta": {"title_en": "An Old Fashioned Boy", "duration": 50, "year": 1920,
                 "original_title": "An Old Fashioned Boy", "director": "Jerome Storm",
                 "country": "United States of America", "genre": "Comedia, Romance"}},
    2: {"search": {"id": 2, "title": "Oldboy", "original_title": "올드보이", "year": 2003},
        "meta": {"title_en": "Oldboy", "title_es": "Oldboy", "duration": 120, "year": 2003,
                 "original_title": "올드보이", "director": "Park Chan-wook",
                 "country": "South Korea", "genre": "Drama, Thriller"}},
    3: {"search": {"id": 3, "title": "Practical Magic 2",
                   "original_title": "Practical Magic 2", "year": 2026},
        "meta": {"title_en": "Practical Magic 2", "title_es": "Hechizo de Amor: La Magia Continúa",
                 "duration": 110, "year": 2026, "original_title": "Practical Magic 2",
                 "director": "Susanne Bier", "country": "United States of America",
                 "genre": "Comedia, Fantasía"}},
    4: {"search": {"id": 4, "title": "One Piece Film: Gold",
                   "original_title": "ONE PIECE FILM GOLD", "year": 2016},
        "meta": {"title_en": "One Piece Film: Gold", "duration": 120, "year": 2016,
                 "original_title": "ONE PIECE FILM GOLD", "director": "Hiroaki Miyamoto",
                 "country": "Japan", "genre": "Acción, Animación"}},
}

BUSQUEDAS = {
    # El orden es el que rompía: primero la de 1920, que matchea el título letra
    # por letra, y después la de Park Chan-wook.
    "OLD BOY": [CATALOGO[1]["search"], CATALOGO[2]["search"]],
    "HECHIZO DE AMOR: LA MAGIA CONTINUA": [CATALOGO[3]["search"]],
    "One Piece Gold": [CATALOGO[4]["search"]],
}

pedidas: list[int] = []  # ids cuya ficha completa se llegó a pedir


def _fetch(movie_id: int) -> dict:
    pedidas.append(movie_id)
    return dict(CATALOGO[movie_id]["meta"])


letterboxd._tmdb_credential = lambda: ("api_key", "fake")
letterboxd.tmdb_search_movie = lambda q, year=None: [dict(c) for c in BUSQUEDAS.get(q, [])]
letterboxd.fetch_tmdb_movie_meta = _fetch


def enriquecer(title: str, hint_duration=None, meta=None) -> dict:
    """El último paso de enrich_title: empty meta + TMDb, sin año ni director."""
    return fill_meta_from_tmdb(meta if meta is not None else _empty_meta(title),
                               title, None, "", "", hint_duration)


# --- El caso del mail ------------------------------------------------------
# Cacodelphia anuncia 119 minutos: la de 50 se descarta y sigue la búsqueda.
m = enriquecer("OLD BOY", hint_duration=119)
assert m["director"] == "Park Chan-wook", m["director"]
assert m["year"] == 2003, m["year"]
assert m["original_title"] == "올드보이", m["original_title"]
assert pedidas == [1, 2], pedidas  # se miró la de 1920 y se la salteó
print("✓ Con la duración del cine, 'OLD BOY' cae en el Oldboy de Park Chan-wook")

# Sin duración publicada no hay con qué desambiguar y vuelve a ganar la de 1920.
# Queda documentado: para esos casos está data/metadata_overrides.json.
m = enriquecer("OLD BOY")
assert m["director"] == "Jerome Storm", m["director"]
print("✓ Sin duración no hay validación posible (y por eso existe el override)")


# --- Que no se lleve puesta la metadata legítima ---------------------------
# Los cines anuncian el bloque con trailers: 130 minutos para una película de
# 110 es la diferencia legítima más grande que había en la cartelera del
# 10/9/2026, y tiene que pasar.
m = enriquecer("HECHIZO DE AMOR: LA MAGIA CONTINUA", hint_duration=130)
assert m["director"] == "Susanne Bier", m["director"]
assert m["title_es"] == "Hechizo de Amor: La Magia Continúa", m["title_es"]
print(f"✓ 130 anunciados vs 110 reales entran en la tolerancia de ±{_TMDB_DUR_TOL}")

# El precio aceptado: si el cine publica un disparate —Hoyts anunciaba One Piece
# Gold en 57 minutos— la película se queda sin metadata. Mejor vacío que otra
# película, que es la regla del resto del enrichment.
m = enriquecer("One Piece Gold", hint_duration=57)
assert not m["director"], m["director"]
print("✓ Una duración disparatada del cine deja la ficha vacía, no equivocada")


# --- La duración que ya sabemos también valida -----------------------------
# Si Letterboxd contestó pero le faltan campos, su duración vale como hint
# aunque el cine no publique ninguna.
parcial = dict(_empty_meta("OLD BOY"), duration=120, url="https://letterboxd.com/film/oldboy/")
m = enriquecer("OLD BOY", meta=parcial)
assert m["director"] == "Park Chan-wook", m["director"]
print("✓ La duración que ya trae el match también descarta candidatos")

print("✓ OK")
