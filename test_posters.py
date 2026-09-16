#!/usr/bin/env python3
"""
Test local del director leído del poster de Cacodelphia, sin red ni API:

    python3 test_posters.py

Los créditos son los de los posters reales de la cartelera del 16/9/2026. El
caso que lo motivó es Nazareno Cruz y el lobo: sin director, la única película
que se llama así quedaba afuera porque Letterboxd le da 85 minutos y el cine 92.
"""
import json
import os
import tempfile
from pathlib import Path

import posters
import scraper
from letterboxd import _decidir_sin_hints, _validate_meta
from posters import director_valido
from scraper import Screening, _caco_completar


# --- El crédito tiene que respaldar al director ------------------------------
assert director_valido("Leonardo Favio", "un film de Leonardo Favio") == "Leonardo Favio"
assert director_valido("Leandro Cerro", "dirigida por Leandro Cerro") == "Leandro Cerro"
assert director_valido("Dylan Southern", "ESCRITA Y DIRIGIDA POR DYLAN SOUTHERN") == "Dylan Southern"
assert director_valido("Gus Van Sant", "Del legendario director Gus Van Sant") == "Gus Van Sant"
assert director_valido("Cédric Klapisch", "UNA PELÍCULA DE CÉDRIC KLAPISCH") == "Cédric Klapisch"
assert director_valido("Park Chan-wook", "Directed by Park Chan-wook") == "Park Chan-wook"
print("✓ créditos de dirección: película de / film de / dirigida por / director / directed by")

# Menciones que no son crédito de dirección.
assert director_valido("Leonardo Favio", "Retrospectiva Leonardo Favio") == ""
assert director_valido("Max Porter", "Basada en el best seller de Max Porter") == ""
assert director_valido("Silvina Pachelo", "Coordinación general Silvina Pachelo") == ""
print("✓ una retrospectiva, una novela o una coordinación no son crédito")

# El nombre tiene que estar escrito en el fragmento: si el modelo "sabe" el
# director en vez de leerlo, no pasa.
assert director_valido("Leonardo Favio", "una película de Pablo Aparo") == ""
assert director_valido("Leonardo Favio", "") == ""
assert director_valido("", "un film de Leonardo Favio") == ""
assert director_valido("Estreno 2026", "una película estreno 2026") == ""
print("✓ un nombre que no está en el fragmento, o sin fragmento, se descarta")


# --- Caché y clave -------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    posters.POSTERS_JSON = Path(tmp) / "posters.json"
    url = "https://apiv2.gaf.adro.studio/uploads/86/poster/nazareno.webp"
    clave = os.environ.pop("ANTHROPIC_API_KEY", None)

    # Sin clave y sin caché no se lee nada, ni se intenta.
    llamadas = []
    posters._leer = lambda *a: llamadas.append(a) or {"director": "X", "credito": "de X"}
    assert posters.director_del_poster(url, "Nazareno Cruz y el lobo") == ""
    assert llamadas == []
    print("✓ sin ANTHROPIC_API_KEY no se llama a la API")

    # Con clave se lee una vez y queda en el caché con la respuesta cruda.
    os.environ["ANTHROPIC_API_KEY"] = "test"
    posters._bajar = lambda u: (b"RIFF....WEBP", "image/webp")
    posters._leer = lambda img, mt, titulo: llamadas.append(titulo) or {
        "director": "Leonardo Favio", "credito": "un film de Leonardo Favio"}
    assert posters.director_del_poster(url, "Nazareno Cruz y el lobo") == "Leonardo Favio"
    assert posters.director_del_poster(url, "Nazareno Cruz y el lobo") == "Leonardo Favio"
    assert llamadas == ["Nazareno Cruz y el lobo"]
    guardado = json.loads(posters.POSTERS_JSON.read_text())
    assert guardado[url]["credito"] == "un film de Leonardo Favio"
    print("✓ cada poster se lee una sola vez y queda en data/posters.json")

    # El control se aplica al leer el caché: una respuesta vieja que no pasa
    # la regla actual no se usa.
    guardado["https://x/gatica.webp"] = {"director": "Leonardo Favio",
                                         "credito": "Retrospectiva Leonardo Favio"}
    posters.POSTERS_JSON.write_text(json.dumps(guardado))
    assert posters.director_del_poster("https://x/gatica.webp", "Gatica el mono") == ""
    print("✓ el caché se revisa con la regla vigente")

    # Un error de la API no se guarda: se reintenta en la próxima corrida.
    posters._leer = lambda *a: None
    assert posters.director_del_poster("https://x/otra.webp", "Otra") == ""
    assert "https://x/otra.webp" not in json.loads(posters.POSTERS_JSON.read_text())
    print("✓ un error de la API no queda cacheado")

    if clave is None:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        os.environ["ANTHROPIC_API_KEY"] = clave


# --- Cruce de funciones con las fichas de la API -----------------------------
PREF_NAZ = "9c388b8cb8ccfd5f77aa3771505f66e7"
fichas = [
    {"pref": PREF_NAZ, "titulo": "NAZARENO CRUZ Y EL LOBO", "duracion": 92,
     "poster": "https://x/nazareno.webp"},
    {"pref": "a" * 32, "titulo": "TANGALANGA CONTRAATACA LA REVANCHA", "duracion": 80,
     "poster": "https://x/tangalanga.webp"},
    {"pref": "b" * 32, "titulo": "OLD BOY", "duracion": 119, "poster": "https://x/oldboy.webp"},
    {"pref": "c" * 32, "titulo": "ISLANDIA", "duracion": 94, "poster": ""},
]
leidos = []


def leer(url, titulo):
    leidos.append(url)
    return {"https://x/nazareno.webp": "Leonardo Favio",
            "https://x/tangalanga.webp": "Dr. Tangalanga"}.get(url, "")


funciones = [
    # Del mail: el link trae el pref, el título viene distinto.
    Screening("Cacodelphia", "Nazareno Cruz y el Lobo", "2026-09-16", "19:00",
              ticket_url=f"https://cineartecacodelphia.com.ar/pelicula/86/{PREF_NAZ}"),
    Screening("Cacodelphia", "NAZARENO CRUZ Y EL LOBO", "2026-09-16", "21:00",
              ticket_url="https://cineartecacodelphia.com.ar/"),
    # El h3 del mail viene truncado.
    Screening("Cacodelphia", "TANGALANGA CONTRAATACA...", "2026-09-17", "20:00"),
    # Lo que ya trajo la SPA no se pisa.
    Screening("Cacodelphia", "Old Boy", "2026-09-18", "22:00", duration=120,
              director="Park Chan-wook"),
    Screening("Cacodelphia", "Islandia", "2026-09-18", "19:00"),
    Screening("Cacodelphia", "Una que no está", "2026-09-18", "19:00"),
]
_caco_completar(funciones, fichas=fichas, leer_poster=leer)
print()
naz1, naz2, tanga, oldboy, islandia, otra = funciones
assert (naz1.director, naz1.duration) == ("Leonardo Favio", 92)
assert (naz2.director, naz2.duration) == ("Leonardo Favio", 92)
assert (tanga.director, tanga.duration) == ("Dr. Tangalanga", 80)
assert (oldboy.director, oldboy.duration) == ("Park Chan-wook", 120)
assert (islandia.director, islandia.duration) == ("", 94)
assert (otra.director, otra.duration) == ("", None)
assert sorted(leidos) == ["https://x/nazareno.webp", "https://x/tangalanga.webp"]
print("✓ fichas: por pref, por título y por título truncado; un poster por película; no pisa la SPA")

# Un prefijo que matchea dos fichas no elige ninguna.
ambigua = [Screening("Cacodelphia", "LOS COLORES DEL...", "2026-09-18", "19:00")]
_caco_completar(ambigua, fichas=[
    {"pref": "d" * 32, "titulo": "LOS COLORES DEL TIEMPO", "duracion": 126, "poster": ""},
    {"pref": "e" * 32, "titulo": "LOS COLORES DEL AGUA", "duracion": 90, "poster": ""},
], leer_poster=leer)
print()
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
print(f"✓ sin director queda vacía, con el motivo real: {motivo}")

# Con el director del poster entra.
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
