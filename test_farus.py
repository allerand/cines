#!/usr/bin/env python3
"""
Test local del scraper de Cineclub Farus (Central Ticket), sin red:

    python3 test_farus.py

Los eventos son los reales de septiembre a noviembre de 2026, recortados a lo
que usa el scraper. El caso de noviembre es el que dejó a Farus dos semanas
fuera de la web: el taplink fijo con los eventos de octubre (que la API ya no
devuelve), el del mes en otra dirección, y la búsqueda con slugs en mayúsculas.
"""
import json
import os
from datetime import date

import scraper
from scraper import _farus_evento, _farus_funcion

# --- Entradas → (película, hora) ---------------------------------------------
assert _farus_funcion("TRAINSPOTTING 8 PM + CONSUMISIÓN") == ("TRAINSPOTTING", "20:00")
assert _farus_funcion("LA HAINE 10:15 PM + CONSUMISIÓN") == ("LA HAINE", "22:15")
assert _farus_funcion("HEAT 8 PM + CONSUMICIÓN") == ("HEAT", "20:00")
assert _farus_funcion("OLDBOY 10.15 PM") == ("OLDBOY", "22:15")
assert _farus_funcion("HEAT 20HS") == ("HEAT", "20:00")
print("✓ entradas: '8 PM', '10:15 PM', '10.15 PM', '20HS'")

assert _farus_funcion("ROSEMARY´S BABY 9 PM + CONSUMISIÓN") == ("ROSEMARY'S BABY", "21:00")
print("✓ el acento agudo de ROSEMARY´S se normaliza a apóstrofo")

assert _farus_funcion("TRAINSPOTTING/LA HAINE 8 PM + 2 CONSUMISIONES") is None
assert _farus_funcion("ENTRADA GENERAL") is None
assert _farus_funcion("") is None
print("✓ la combinada de la doble función y una entrada sin hora no son funciones")


# --- Un evento de Central Ticket ---------------------------------------------
doble = {
    "id": 10411, "name": "Cineclub Farus - Doble Función", "published": True,
    # 20:00 en Buenos Aires
    "date": "2026-09-20T23:00:00.000Z",
    "items": [
        {"id": 33866, "name": "TRAINSPOTTING 8 PM + CONSUMISIÓN"},
        {"id": 33867, "name": "LA HAINE 10:15 PM + CONSUMISIÓN"},
        {"id": 33868, "name": "TRAINSPOTTING/LA HAINE 8 PM + 2 CONSUMISIONES"},
    ],
}
fs = _farus_evento(doble, "cineclubfarusdoblefuncion2")
assert [(s.fecha, s.hora, s.title) for s in fs] == [
    ("2026-09-20", "20:00", "TRAINSPOTTING"), ("2026-09-20", "22:15", "LA HAINE")], fs
assert all(s.cine == "Cineclub Farus" for s in fs)
assert fs[0].ticket_url == "https://centralticket.net/event/cineclubfarusdoblefuncion2"
print("✓ doble función: dos películas, con la hora de cada entrada (La Haine 22:15)")

# La fecha es la de Buenos Aires, no la UTC: 21:00 del 18 es 00:00 del 19 en UTC.
rosemary = {"id": 10409, "name": "Cineclub Farus", "date": "2026-09-19T00:00:00.000Z",
            "items": [{"name": "ROSEMARY´S BABY 9 PM + CONSUMISIÓN"}]}
fs = _farus_evento(rosemary, "cineclubfarusvol4")
assert [(s.fecha, s.hora) for s in fs] == [("2026-09-18", "21:00")], fs
print("✓ la fecha sale en hora de Buenos Aires (Rosemary's Baby, viernes 18)")


assert _farus_funcion("Batman 7 PM + CONSUMICIÓN") == ("Batman", "19:00")
assert _farus_funcion("Star Wars: Episode V 6.30PM + CONSUMICIÓN") == ("Star Wars: Episode V", "18:30")
assert _farus_funcion("La Masacre De Texas 9.40PM + CONSUMICIÓN") == ("La Masacre De Texas", "21:40")
assert _farus_funcion("12 Angry Men 10PM + CONSUMICIÓN") == ("12 Angry Men", "22:00")
print("✓ entradas de octubre: '7 PM', '6.30PM', '9.40PM', y un título que empieza con número")

# La combinada ahora separa con "|" en vez de "/".
assert _farus_funcion("Batman | The Matrix  + 2 CONSUMICIONES") is None
assert _farus_funcion("Evil Dead | La Masacre de Texas  (8PM)  + 2 CONSUMICIONES") is None
print("✓ la combinada de la doble función, separe con / o con |, no es una función")


# --- Noviembre: entradas con "20h" y la triple del Ciclo Giallo ---------------
assert _farus_funcion("Le bonheur 20h + Consumición") == ("Le bonheur", "20:00")
assert _farus_funcion("Lawrence of Arabia 20h + Consumición") == ("Lawrence of Arabia", "20:00")
# La hora entre paréntesis, como en la descripción de la triple.
assert _farus_funcion("Dont Torture a Duckling (20.40h)") == ("Dont Torture a Duckling", "20:40")
assert _farus_funcion("Blood and Black Lace (19h)") == ("Blood and Black Lace", "19:00")
# Las 00 son medianoche, no el mediodía.
assert _farus_funcion("Deep Red (00h)") == ("Deep Red", "00:00")
# Las entradas de la triple no nombran películas.
assert _farus_funcion("1 Pelicula a elección + 1 Consumición (bebida)") is None
assert _farus_funcion("2 peliculas a elección + 2 Consumiciones (bebidas)") is None
assert _farus_funcion('"La Noche Completa" + 5 consumicones (3 comida + 2 bebidas)') is None
# Un número entre paréntesis no es una hora.
assert _farus_funcion("Parte (1)") is None
print("✓ entradas de noviembre ('20h'), la hora entre paréntesis y las 00 como medianoche")

# El evento real del 27/11/2026, recortado: las películas están sólo en la
# descripción.
triple = {
    "id": 11199, "name": "Cineclub Farus - Triple Función", "groupId": 2025,
    "published": True, "date": "2026-11-27T22:00:00.000Z",
    "description": (
        "CICLO GIALLO! El Viernes 27 de Noviembre los esperamos para ver tres peliculas! \r\n"
        "- Blood and Black Lace (19h)\r\n- Dont Torture a Duckling (20.40h)\r\n"
        "- Deep Red (22.45h)\r\n\r\nA las 18hs abrimos la antesala para encontrarnos y "
        "conocernos. Después, charlamos!\r\n\r\n*Tres tipos de entrada:*\r\n"
        "• 1 Pelicula a elección + 1 Consumición (bebida)🎟 $10.000\r\n"
        "• 2 peliculas a elección + 2 Consumiciónes (bebidas) 🎟 $18.000\r\n"
        "• \"La Noche Completa\" 3 peliculas + 5 consumiciones (3 comida + 2 bebidas) 🎟 $28.000"
        "\r\n\r\n📍 Venezuela 930, Monserrat — Paradiso Cultural 📅 Viernes 27 de noviembre"),
    "items": [{"name": "1 Pelicula a elección + 1 Consumición (bebida)"},
              {"name": "2 peliculas a elección + 2 Consumiciones (bebidas)"},
              {"name": "\"La Noche Completa\" + 5 consumicones (3 comida + 2 bebidas)"}],
}
fs = _farus_evento(triple, "11199")
assert [(s.fecha, s.hora, s.title, s.ciclo) for s in fs] == [
    ("2026-11-27", "19:00", "Blood and Black Lace", "Ciclo Giallo"),
    ("2026-11-27", "20:40", "Dont Torture a Duckling", "Ciclo Giallo"),
    ("2026-11-27", "22:45", "Deep Red", "Ciclo Giallo"),
], fs
assert fs[0].ticket_url == "https://centralticket.net/event/11199"
print("✓ triple: si las entradas no nombran películas, salen de la descripción, con el ciclo")

# Con el horario del taplink (20, 22 y 00 h), la de las 00 es del día siguiente.
trasnoche = dict(triple, description="CICLO GIALLO!\n- Blood and Black Lace (20h)\n"
                                     "- Dont Torture a Duckling (22h)\n- Deep Red (00h)\n")
fs = _farus_evento(trasnoche, "11199")
assert [(s.fecha, s.hora) for s in fs] == [
    ("2026-11-27", "20:00"), ("2026-11-27", "22:00"), ("2026-11-28", "00:00")], fs
print("✓ una película de madrugada en un evento de noche va al día siguiente")

# Una función suelta: la entrada manda y la descripción en prosa no agrega nada.
bonheur = {
    "id": 11190, "name": "Cineclub Farus", "groupId": 2025, "published": True,
    "date": "2026-11-22T23:00:00.000Z", "lineUpsString": ["Farus"],
    "description": ("El Domingo 22 de noviembre los esperamos para ver Le Bonheur (La "
                    "Felicidad) 20hrs. A las 19.30hs abrimos la antesala para encontrarnos "
                    "y conocernos. Después, charlamos!\r\n\r\nTres tipos de entrada:\r\n"
                    "* Le bonheur 20h + Consumición 🎟️ 10.000"),
    "items": [{"name": "Le bonheur 20h + Consumición"}],
}
fs = _farus_evento(bonheur, "11190")
assert [(s.fecha, s.hora, s.title, s.ciclo) for s in fs] == [
    ("2026-11-22", "20:00", "Le bonheur", "")], fs
print("✓ función suelta: la de la entrada, sin ciclo")


# --- Descubrimiento ----------------------------------------------------------
assert scraper._farus_taplinks(date(2026, 11, 15)) == [
    "https://cineclubfarus.taplink.bio/",
    "https://cineclubfarusnoviembre.taplink.bio/", "https://cineclubfarusnoviembre.taplink.ws/",
    "https://cineclubfarusdiciembre.taplink.bio/", "https://cineclubfarusdiciembre.taplink.ws/",
]
assert scraper._farus_taplinks(date(2026, 10, 3)) == [
    "https://cineclubfarus.taplink.bio/",
    "https://cineclubfarusseptiembre.taplink.bio/", "https://cineclubfarusseptiembre.taplink.ws/",
    "https://cineclubfarussetiembre.taplink.bio/", "https://cineclubfarussetiembre.taplink.ws/",
    "https://cineclubfarusoctubre.taplink.bio/", "https://cineclubfarusoctubre.taplink.ws/",
]
print("✓ taplinks del mes: el de hace una semana, el de hoy y el de dentro de 24 días")

# Septiembre: la búsqueda listaba los slugs con "farus".
BUSQUEDA_SEPT = """
<a href="/event/cineclubfarusdoblefuncion2">Cineclub Farus - Doble Función</a>
<a href="/event/cineclubfarusvol4">Cineclub Farus</a>
<a href="/event/cineclubfarusvol4">Cineclub Farus</a>
<a href="/event/fiesta-faruscopia">Otra cosa</a>
"""
# Octubre: el taplink fijo, con ids numéricos.
TAPLINK_OCT = """
{"options":{"title":"4/10 BATMAN | THE MATRIX","value":"https://centralticket.net/10737?refer=2504"}},
{"options":{"title":"18/9 - Rosemary's Baby","value":"https://centralticket.net/10409?refer=2504"}},
{"options":{"title":"Seguinos","value":"https://instagram.com/cineclubfarus"}}
"""
# Noviembre: el fijo quedó con octubre y el del mes es otro perfil.
TAPLINK_FIJO_NOV = """
{"options":{"title":"21/10 Stand By Me - 12 Angry Men","value":"https://centralticket.net/10741?refer=2504"}},
{"options":{"title":"28/10 | The Evil Dead - La Masacre de Texas","value":"https://centralticket.net/10743?refer=2504"}}
"""
TAPLINK_NOVIEMBRE = """
{"options":{"title":"22/11 - 20h Le Bonheur","value":"https://centralticket.net/11190?refer=2504"}},
{"options":{"title":"27/11 - CICLO GIALLO ","value":"https://centralticket.net/11199?refer=2504",
 "subtitle":"- Blood and Black Lace (20h) - Dont Torture a Duckling (22h) - Deep Red (00h)"}}
"""
# La búsqueda real de noviembre: tres tarjetas con slugs en mayúsculas y el
# catálogo de todo el sitio embebido.
BUSQUEDA_NOV = """
<a href="/event/2211CineclubFarus" data-sveltekit-preload-data="tap" id="search-card-11190" class="x">
<a href="/event/2511CineclubFarus" data-sveltekit-preload-data="tap" id="search-card-11191" class="x">
<a href="/event/2711TFCineclubFarus" data-sveltekit-preload-data="tap" id="search-card-11199" class="x">
<script>data:[{id:"10983",eventURL:"oasis",href:"/event/oasis",title:"OASIS",venue:"Camping Soever",
dateParts:{day:"7",monthShort:"Nov",year:"2026"},artists:["Oasis"],dateStartKey:"2026-11-07",dateEndKey:"2026-11-07"},
{id:"11190",eventURL:"2211CineclubFarus",href:"/event/2211CineclubFarus",title:"Cineclub Farus",
venue:"Paradiso Cultural",dateParts:{day:"22",monthShort:"Nov",year:"2026"},artists:["Farus"],
coordinates:{latitude:-34.61,longitude:-58.37},dateStartKey:"2026-11-22",dateEndKey:"2026-11-22"},
{id:"11191",eventURL:"2511CineclubFarus",href:"/event/2511CineclubFarus",title:"Cineclub Farus",
venue:"Paradiso Cultural",artists:["Farus"],dateStartKey:"2026-11-25",dateEndKey:"2026-11-25"},
{id:"11199",eventURL:"2711TFCineclubFarus",href:"/event/2711TFCineclubFarus",
title:"Cineclub Farus - Triple Función",venue:"Paradiso Cultural",artists:["Cineclub Farus"],
dateStartKey:"2026-11-27",dateEndKey:"2026-11-28"}]</script>
"""
lawrence = {"id": 11191, "name": "Cineclub Farus", "groupId": 2025, "published": True,
            "date": "2026-11-25T23:00:00.000Z",
            "items": [{"name": "Lawrence of Arabia 20h + Consumición"}]}

EVENTOS = {
    "cineclubfarusdoblefuncion2": doble, "10411": doble,
    "cineclubfarusvol4": rosemary, "10409": rosemary,
    "fiesta-faruscopia": {"id": 10500, "name": "Fiesta de otra productora",
                          "date": "2026-09-19T03:00:00.000Z", "items": [{"name": "PISTA 1 AM"}]},
    "10737": {"id": 10737, "name": "Cineclub Farus - Doble Función", "groupId": 2025,
              "date": "2026-10-04T22:00:00.000Z",
              "items": [{"name": "Batman 7 PM + CONSUMICIÓN"},
                        {"name": "The Matrix 9.30 PM + CONSUMICIÓN"},
                        {"name": "Batman | The Matrix  + 2 CONSUMICIONES"}]},
    # Un evento ajeno linkeado desde el taplink no entra.
    "99999": {"id": 99999, "name": "Fiesta de otra productora", "groupId": 7,
              "date": "2026-10-05T03:00:00.000Z", "items": [{"name": "PISTA 1 AM"}]},
    # La API devuelve los eventos por id o por slug, pero el slug tiene que ir
    # como viene: en minúsculas devuelve vacío (y los de octubre, ya ni por id).
    "11190": bonheur, "2211CineclubFarus": bonheur,
    "11191": lawrence, "2511CineclubFarus": lawrence,
    "11199": triple, "2711TFCineclubFarus": triple,
}

PAGINAS: dict = {}
pedidos: list = []


def fetch_falso(url, *a, **k):
    pedidos.append(url)
    if url in PAGINAS:
        if PAGINAS[url] is None:
            raise OSError("no contesta")
        return PAGINAS[url].encode()
    if url.startswith("https://centralticket.net/api/event/getOne/"):
        ev = EVENTOS.get(url.rsplit("/", 1)[-1])
        return json.dumps(ev).encode() if ev else b""     # así contesta la API
    # Un taplink que no existe redirige a la home de Taplink.
    return b"<html>Taplink: la mejor bio de Instagram</html>"


class HoyFijo(scraper.date):
    hoy = (2026, 9, 17)

    @classmethod
    def today(cls):
        return cls(*cls.hoy)


def correr(hoy, paginas):
    HoyFijo.hoy = hoy
    PAGINAS.clear()
    PAGINAS.update(paginas)
    pedidos.clear()
    scraper.FUENTES_CAIDAS.clear()
    fs = scraper.scrape_farus(9)
    return sorted((s.fecha, s.hora, s.title) for s in fs)


scraper.fetch_bytes = fetch_falso
scraper.date = HoyFijo
os.environ.pop("IG_ACCESS_TOKEN", None)

# Septiembre-octubre: el taplink y la búsqueda se juntan.
fs = correr((2026, 9, 17), {scraper.FARUS_TAPLINK: TAPLINK_OCT, scraper.FARUS_BUSQUEDA: BUSQUEDA_SEPT})
assert fs == [
    ("2026-09-18", "21:00", "ROSEMARY'S BABY"),
    ("2026-09-20", "20:00", "TRAINSPOTTING"),
    ("2026-09-20", "22:15", "LA HAINE"),
    ("2026-10-04", "19:00", "Batman"),
    ("2026-10-04", "21:30", "The Matrix"),
], fs
assert not scraper.FUENTES_CAIDAS
print("✓ el taplink y la búsqueda se suman: lo que falta en uno lo trae el otro")

fs = correr((2026, 9, 17), {scraper.FARUS_TAPLINK: "", scraper.FARUS_BUSQUEDA: BUSQUEDA_SEPT})
assert fs == [
    ("2026-09-18", "21:00", "ROSEMARY'S BABY"),
    ("2026-09-20", "20:00", "TRAINSPOTTING"),
    ("2026-09-20", "22:15", "LA HAINE"),
], fs
print("✓ sin taplink, la búsqueda alcanza; un evento ajeno nunca entra")

# Noviembre, tal cual estaba el 15/11/2026.
NOVIEMBRE = {
    scraper.FARUS_TAPLINK: TAPLINK_FIJO_NOV,
    "https://cineclubfarusnoviembre.taplink.bio/": TAPLINK_NOVIEMBRE,
    scraper.FARUS_BUSQUEDA: BUSQUEDA_NOV,
}
ESPERADO_NOV = [
    ("2026-11-22", "20:00", "Le bonheur"),
    ("2026-11-25", "20:00", "Lawrence of Arabia"),
    ("2026-11-27", "19:00", "Blood and Black Lace"),
    ("2026-11-27", "20:40", "Dont Torture a Duckling"),
    ("2026-11-27", "22:45", "Deep Red"),
]
fs = correr((2026, 11, 15), NOVIEMBRE)
assert fs == ESPERADO_NOV, fs
assert not scraper.FUENTES_CAIDAS, scraper.FUENTES_CAIDAS
# Cada evento se pide una vez, aunque lo traigan el taplink, la tarjeta y el slug.
api = [u for u in pedidos if "/api/event/getOne/" in u]
assert sorted(api) == sorted(scraper.FARUS_API.format(slug=i)
                             for i in ("10741", "10743", "11190", "11191", "11199")), api
print("✓ noviembre: el taplink fijo viejo ya no tapa al del mes ni a la búsqueda")

# Lo que pasó del 29/10 al 15/11: con el fijo viejo y sin el del mes, la
# búsqueda sola tiene que alcanzar.
fs = correr((2026, 11, 15), {scraper.FARUS_TAPLINK: TAPLINK_FIJO_NOV,
                             scraper.FARUS_BUSQUEDA: BUSQUEDA_NOV})
assert fs == ESPERADO_NOV, fs
print("✓ con el taplink fijo viejo y sin el del mes, alcanza la búsqueda")

# Sin catálogo embebido (si cambia el formato), quedan las tarjetas y los slugs,
# que van a la API con sus mayúsculas.
solo_tarjetas = BUSQUEDA_NOV.split("<script>")[0]
fs = correr((2026, 11, 15), {scraper.FARUS_TAPLINK: None, scraper.FARUS_BUSQUEDA: solo_tarjetas})
assert fs == ESPERADO_NOV, fs
solo_slugs = solo_tarjetas.replace('id="search-card-', 'data-x="')
fs = correr((2026, 11, 15), {scraper.FARUS_TAPLINK: None, scraper.FARUS_BUSQUEDA: solo_slugs})
assert fs == ESPERADO_NOV, fs
assert scraper.FARUS_API.format(slug="2211CineclubFarus") in pedidos
assert not any("2211cineclubfarus" in u for u in pedidos)
print("✓ sin catálogo, las tarjetas; sin tarjetas, los slugs con sus mayúsculas")

# El link de la bio de Instagram se sigue, aunque no sea un taplink conocido.
llamadas = []


def graph_falso(path, params, timeout=30):
    llamadas.append(params["fields"])
    return {"business_discovery": {"website": "https://linktr.ee/cineclubfarus?utm=ig"}}


scraper._graph_get = graph_falso
os.environ["IG_ACCESS_TOKEN"] = "token-de-prueba"
fs = correr((2026, 11, 15), {scraper.FARUS_TAPLINK: None, scraper.FARUS_BUSQUEDA: None,
                             "https://linktr.ee/cineclubfarus?utm=ig": TAPLINK_NOVIEMBRE})
assert llamadas == ["business_discovery.username(cineclubfarus){website}"], llamadas
assert fs == [("2026-11-22", "20:00", "Le bonheur"), ("2026-11-27", "19:00", "Blood and Black Lace"),
              ("2026-11-27", "20:40", "Dont Torture a Duckling"),
              ("2026-11-27", "22:45", "Deep Red")], fs
print("✓ el link de la bio de Instagram: si cambia de dirección, se sigue solo")


def graph_caido(path, params, timeout=30):
    raise RuntimeError("Graph API 400: no es una cuenta profesional (code 110)")


scraper._graph_get = graph_caido
fs = correr((2026, 11, 15), NOVIEMBRE)
assert fs == ESPERADO_NOV, fs
os.environ.pop("IG_ACCESS_TOKEN", None)
print("✓ si Instagram no contesta, quedan los taplinks y la búsqueda")

# --- Que se note cuando algo falla --------------------------------------------
fs = correr((2026, 11, 15), {scraper.FARUS_TAPLINK: None, scraper.FARUS_BUSQUEDA: None,
                             **{u: None for u in scraper._farus_taplinks(date(2026, 11, 15))}})
assert fs == []
assert "ninguna de sus fuentes" in scraper.FUENTES_CAIDAS.get("Cineclub Farus", ""), scraper.FUENTES_CAIDAS
print("✓ si no contesta ninguna fuente, la fuente queda marcada como caída")

# Un evento por venir que no dice qué películas da.
sin_peliculas = dict(triple, description="CICLO GIALLO! Tres películas, vení a la noche completa.")
EVENTOS["11199"] = EVENTOS["2711TFCineclubFarus"] = sin_peliculas
fs = correr((2026, 11, 15), NOVIEMBRE)
assert fs == ESPERADO_NOV[:2], fs
motivo = scraper.FUENTES_CAIDAS.get("Cineclub Farus", "")
assert "11199" in motivo and "no dice qué películas da" in motivo, motivo
print("✓ un evento por venir sin películas legibles marca la fuente, con el link")

# Un evento que la búsqueda anuncia y la API no devuelve.
del EVENTOS["11199"], EVENTOS["2711TFCineclubFarus"]
fs = correr((2026, 11, 15), NOVIEMBRE)
assert fs == ESPERADO_NOV[:2], fs
motivo = scraper.FUENTES_CAIDAS.get("Cineclub Farus", "")
assert "no devuelve el evento" in motivo and "11199" in motivo, motivo
# Los eventos viejos del taplink que vuelven vacíos no son un problema.
assert "10741" not in motivo and "10743" not in motivo, motivo
print("✓ un evento anunciado que la API no devuelve también; los viejos del taplink, no")

print("\nTodo OK")
