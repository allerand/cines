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


def fetch_falso(url, *a, **k):
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
    ("2026-09-20", "20:00", "TRAINSPOTTING"),
    ("2026-09-20", "22:15", "LA HAINE"),
], fs
print("✓ búsqueda: cada evento una vez, y uno que no es de Farus queda afuera")

print("\nTodo OK")
