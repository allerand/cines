#!/usr/bin/env python3
"""
Test local de la API de fichas de Cacodelphia y del enrichment de Nazareno Cruz
y el lobo, sin red:

    python3 test_cacodelphia_fichas.py

La API de fichas completa la duración de las funciones que llegan del mail sin
ella. El caso de Nazareno: sin director, la única película que se llama así
quedaba afuera porque Letterboxd le da 85 minutos y el cine 92.
"""
from letterboxd import _decidir_sin_hints, _validate_meta
from scraper import Screening, _caco_completar


# --- Cruce de funciones con las fichas de la API -----------------------------
PREF_NAZ = "9c388b8cb8ccfd5f77aa3771505f66e7"
fichas = [
    {"pref": PREF_NAZ, "titulo": "NAZARENO CRUZ Y EL LOBO", "duracion": 92},
    {"pref": "a" * 32, "titulo": "TANGALANGA CONTRAATACA LA REVANCHA", "duracion": 80},
    {"pref": "b" * 32, "titulo": "OLD BOY", "duracion": 119},
]
funciones = [
    # Del mail: el link trae el pref, el título viene distinto.
    Screening("Cacodelphia", "Nazareno Cruz y el Lobo", "2026-09-16", "19:00",
              ticket_url=f"https://cineartecacodelphia.com.ar/pelicula/86/{PREF_NAZ}"),
    Screening("Cacodelphia", "NAZARENO CRUZ Y EL LOBO", "2026-09-16", "21:00",
              ticket_url="https://cineartecacodelphia.com.ar/"),
    # El h3 del mail viene truncado.
    Screening("Cacodelphia", "TANGALANGA CONTRAATACA...", "2026-09-17", "20:00"),
    # Lo que ya trajo la SPA no se pisa.
    Screening("Cacodelphia", "Old Boy", "2026-09-18", "22:00", duration=120),
    Screening("Cacodelphia", "Una que no está", "2026-09-18", "19:00"),
]
_caco_completar(funciones, fichas=fichas)
assert [s.duration for s in funciones] == [92, 92, 80, 120, None], [s.duration for s in funciones]
print("✓ fichas: por pref, por título y por título truncado; no pisa la duración de la SPA")

# Un prefijo que calza con dos fichas no elige ninguna.
ambigua = [Screening("Cacodelphia", "LOS COLORES DEL...", "2026-09-18", "19:00")]
_caco_completar(ambigua, fichas=[
    {"pref": "d" * 32, "titulo": "LOS COLORES DEL TIEMPO", "duracion": 126},
    {"pref": "e" * 32, "titulo": "LOS COLORES DEL AGUA", "duracion": 90},
])
assert ambigua[0].duration is None
print("✓ un título truncado que calza con dos fichas queda sin completar")


# --- Enrichment: Nazareno Cruz y el lobo -------------------------------------
nazareno = {"url": "https://letterboxd.com/film/nazareno-cruz-and-the-wolf/",
            "title_en": "Nazareno Cruz and the Wolf", "director": "Leonardo Favio",
            "year": 1975, "duration": 85, "country": "Argentina",
            "titulos": ["Nazareno Cruz and the Wolf", "Nazareno Cruz y el lobo"]}

# Sin director: 85 contra 92 la descarta, y el log dice por qué.
elegido, motivo = _decidir_sin_hints(["NAZARENO CRUZ Y EL LOBO", ""], 92,
                                     [(dict(nazareno), "slug")])
assert elegido is None
assert motivo.startswith("se llama así pero no dura 92 min"), motivo
print(f"✓ sin director la regla estricta la deja vacía, con el motivo real: {motivo}")

# Con director confirmado, 7 minutos de diferencia no la descartan.
assert _validate_meta(dict(nazareno), None, "Leonardo Favio", 92)
assert not _validate_meta(dict(nazareno), None, "", 92)
print("✓ con el director confirmado, 7 minutos de diferencia no la descartan")

# Pero no cualquier duración: las dos The Man Who Knew Too Much de Hitchcock.
hitchcock_34 = {"url": "u", "title_en": "The Man Who Knew Too Much", "director": "Alfred Hitchcock",
                "year": 1934, "duration": 75}
assert not _validate_meta(hitchcock_34, None, "Alfred Hitchcock", 120)
# Y un director que no coincide sigue afuera, dure lo que dure.
assert not _validate_meta(dict(nazareno), None, "Pablo Aparo", 85)
print("✓ el mismo director con otra película de otra duración, o otro director, siguen afuera")

print("\nTodo OK")
