#!/usr/bin/env python3
"""
Test local del scraper de Cineclub Farus (Central Ticket), sin red:

    python3 test_farus.py

Los eventos son los reales de septiembre de 2026, recortados a lo que usa el
scraper.
"""
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
rosemary = {"name": "Cineclub Farus", "date": "2026-09-19T00:00:00.000Z",
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


# --- Descubrimiento por la búsqueda ------------------------------------------
BUSQUEDA = """
<a href="/event/cineclubfarusdoblefuncion2">Cineclub Farus - Doble Función</a>
<a href="/event/cineclubfarusvol4">Cineclub Farus</a>
<a href="/event/cineclubfarusvol4">Cineclub Farus</a>
<a href="/event/fiesta-faruscopia">Otra cosa</a>
"""
EVENTOS = {
    "cineclubfarusdoblefuncion2": doble,
    "cineclubfarusvol4": rosemary,
    "fiesta-faruscopia": {"name": "Fiesta de otra productora", "date": "2026-09-19T03:00:00.000Z",
                          "items": [{"name": "PISTA 1 AM"}]},
}


TAPLINK = """
{"options":{"title":"4/10 BATMAN | THE MATRIX","value":"https://centralticket.net/10737?refer=2504"}},
{"options":{"title":"18/9 - Rosemary's Baby","value":"https://centralticket.net/10409?refer=2504"}},
{"options":{"title":"Seguinos","value":"https://instagram.com/cineclubfarus"}}
"""
EVENTOS["10737"] = {"name": "Cineclub Farus - Doble Función", "groupId": 2025,
                    "date": "2026-10-04T22:00:00.000Z",
                    "items": [{"name": "Batman 7 PM + CONSUMICIÓN"},
                              {"name": "The Matrix 9.30 PM + CONSUMICIÓN"},
                              {"name": "Batman | The Matrix  + 2 CONSUMICIONES"}]}
EVENTOS["10409"] = rosemary
# Un evento ajeno linkeado desde el taplink no entra.
EVENTOS["99999"] = {"name": "Fiesta de otra productora", "groupId": 7,
                    "date": "2026-10-05T03:00:00.000Z", "items": [{"name": "PISTA 1 AM"}]}

taplink_vacio = False


def fetch_falso(url, *a, **k):
    if url == scraper.FARUS_TAPLINK:
        return b"" if taplink_vacio else TAPLINK.encode()
    if url == scraper.FARUS_BUSQUEDA:
        return BUSQUEDA.encode()
    slug = url.rsplit("/", 1)[-1]
    import json
    return json.dumps(EVENTOS[slug]).encode()


class HoyFijo(scraper.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 17)


scraper.fetch_bytes = fetch_falso
scraper.date = HoyFijo
fs = scraper.scrape_farus(9)
assert sorted((s.fecha, s.hora, s.title) for s in fs) == [
    ("2026-09-18", "21:00", "ROSEMARY'S BABY"),
    ("2026-10-04", "19:00", "Batman"),
    ("2026-10-04", "21:30", "The Matrix"),
], fs
print("✓ taplink: los eventos que linkea, con los ids numéricos de Central Ticket")

# Los eventos de octubre son /10737, /10738… sin "farus" en la dirección: si el
# taplink se cae, la búsqueda sólo pesca los slugs viejos.
taplink_vacio = True
fs = scraper.scrape_farus(9)
assert sorted((s.fecha, s.hora, s.title) for s in fs) == [
    ("2026-09-18", "21:00", "ROSEMARY'S BABY"),
    ("2026-09-20", "20:00", "TRAINSPOTTING"),
    ("2026-09-20", "22:15", "LA HAINE"),
], fs
print("✓ sin taplink, la búsqueda queda de respaldo; un evento ajeno nunca entra")

print("\nTodo OK")
