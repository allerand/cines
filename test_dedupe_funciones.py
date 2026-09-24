#!/usr/bin/env python3
"""
Tests de lo que evita que una función se publique dos veces en la misma sala.

    python3 test_dedupe_funciones.py

Lo motiva FIC.UBA 2026. La grilla del festival se carga entera a mano desde la
guía en PDF, también en salas que ya se scrapean, y cada sala publica el
festival a su manera:

- La Sala Lugones lo publica en el CTBA con otra caja ("La Perra" contra
  "La perra" de la guía) y a veces con otra fecha (La hija cóndor el 30/9 en
  vez del 1/10).
- El Cosmos arma la cartelera de jueves a lunes con el mismo horario todos los
  días ("Ju Vi Sá Do Lu | 21:00"): una película que da una vez sale cinco.
- Cacodelphia le pega el festival al título.

Dos defensas: aplicar_festivales (scraper.py), que en las salas y fechas del
festival deja mandar a la guía, y la deduplicación final de run.py, que
compara el título normalizado dentro de cada horario.
"""
import re
import sys
import textwrap
from pathlib import Path

from scraper import Screening, aplicar_festivales, misma_pelicula, titulo_norm

ROOT = Path(__file__).parent
fallas = 0


def ok(nombre, obtuvo, esperado):
    global fallas
    if obtuvo == esperado:
        print(f"  ✅ {nombre}")
    else:
        fallas += 1
        print(f"  ❌ {nombre}\n     esperado {esperado}\n     obtuvo   {obtuvo}")


# --- Deduplicación final de run.py --------------------------------------------

def dedupe_de_run(screenings_out):
    """Corre el bloque de dedupe de run.py. Se extrae del fuente en vez de
    importar run.py porque importarlo arranca playwright y pide red."""
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    ini = src.index("    vistas: dict[tuple, list[str]] = {}")
    fin = src.index("    if len(unicas) != len(screenings_out):")
    ns = {"screenings_out": screenings_out, "re": re,
          "titulo_norm": titulo_norm, "misma_pelicula": misma_pelicula}
    exec(textwrap.dedent(src[ini:fin]), ns)
    return [(s["cine"], s["title_es"], s["hora"]) for s in ns["unicas"]]


def f(cine, title, fecha="2026-10-04", hora="21:00"):
    return {"cine": cine, "title_es": title, "fecha": fecha, "hora": hora}


print("Deduplicación final (run.py)")

ok("misma película con otra caja: queda la primera (la manual)",
   dedupe_de_run([f("Sala Lugones", "La perra"), f("Sala Lugones", "La Perra")]),
   [("Sala Lugones", "La perra", "21:00")])

ok("apóstrofo curvo contra recto",
   dedupe_de_run([f("Sala Lugones", "Le Journal d'une femme de chambre"),
                  f("Sala Lugones", "Le Journal d’une femme de chambre")]),
   [("Sala Lugones", "Le Journal d'une femme de chambre", "21:00")])

ok("un título contiene al otro (título original, festival pegado)",
   dedupe_de_run([f("Cacodelphia", "Tierra de mi padre"),
                  f("Cacodelphia", "Fatherland (Tierra de mi padre)"),
                  f("Cacodelphia", "La perra"), f("Cacodelphia", "La perra - FIC.UBA")]),
   [("Cacodelphia", "Tierra de mi padre", "21:00"), ("Cacodelphia", "La perra", "21:00")])

ok("dos películas distintas en el mismo horario se quedan",
   dedupe_de_run([f("Cacodelphia", "C'est pas moi", hora="17:30"),
                  f("Cacodelphia", "Boy Meets Girl", hora="17:30")]),
   [("Cacodelphia", "C'est pas moi", "17:30"), ("Cacodelphia", "Boy Meets Girl", "17:30")])

ok("un título corto no se come a otro que lo contiene de casualidad",
   dedupe_de_run([f("Cacodelphia", "Oca"), f("Cacodelphia", "Oca Loca")]),
   [("Cacodelphia", "Oca", "21:00"), ("Cacodelphia", "Oca Loca", "21:00")])

ok("misma película en otro horario, otra sala u otro día: no es duplicado",
   dedupe_de_run([f("Cacodelphia", "La perra", hora="13:45"), f("Cacodelphia", "La perra"),
                  f("Sala Lugones", "La perra"), f("Cacodelphia", "La perra", fecha="2026-10-03")]),
   [("Cacodelphia", "La perra", "13:45"), ("Cacodelphia", "La perra", "21:00"),
    ("Sala Lugones", "La perra", "21:00"), ("Cacodelphia", "La perra", "21:00")])


# --- aplicar_festivales (scraper.py) ------------------------------------------

PAN = "FICUBA - Panorama internacional"
INTL = "FICUBA - Competencia internacional de largometrajes"
UBAC = "FICUBA - Competencia de cortometrajes UBA"
# Lo que el CTBA le pone a las funciones del festival en el Lugones.
CTBA = "FIC.UBA - Festival Internacional de Cine de la UBA"
GRILLA = {
    "screenings": [
        {"cine": "Cine Cosmos", "title": "La libertad doble", "fecha": "2026-10-02",
         "hora": "21:00", "ciclo": "FICUBA - Proyecciones especiales"},
        {"cine": "Cine Cosmos", "title": "Cortometrajes UBA – Programa 1",
         "fecha": "2026-10-04", "hora": "16:00", "ciclo": UBAC,
         "cortos": ["El último Turf", "La hora de la siesta"]},
        {"cine": "Sala Lugones", "title": "La hija cóndor", "fecha": "2026-10-01",
         "hora": "15:00", "ciclo": INTL},
        {"cine": "Sala Lugones", "title": "Imperium", "fecha": "2026-09-30",
         "hora": "14:00", "ciclo": PAN},
        # Otro ciclo que no es del festival: no cuenta como grilla.
        {"cine": "Cine Cosmos", "title": "Ficubano", "fecha": "2026-10-03",
         "hora": "12:00", "ciclo": "FICUBANOS"},
    ],
    "festivales": [{"ciclo": "FICUBA", "desde": "2026-09-30", "hasta": "2026-10-07",
                    "cines": ["Cine Cosmos", "Sala Lugones"]}],
}


def manual(m):
    return Screening(cine=m["cine"], title=m["title"], fecha=m["fecha"],
                     hora=m["hora"], ciclo=m["ciclo"])


def sala(cine, title, fecha, hora, ciclo=""):
    return Screening(cine=cine, title=title, fecha=fecha, hora=hora, ciclo=ciclo)


def festival(screenings):
    quedan, _ = aplicar_festivales(screenings, GRILLA)
    return [(s.cine, s.title, s.fecha, s.hora) for s in quedan]


print("\nFestivales cargados a mano (scraper.aplicar_festivales)")

grilla = [manual(m) for m in GRILLA["screenings"] if m["ciclo"].startswith("FICUBA - ")]

# El Cosmos publica La libertad doble "Ju Vi Sá Do Lu | 21:00": el scraper la
# expande a cinco días. Sólo vale la del viernes 2, que ya está en la grilla.
cosmos_jue_a_lun = [sala("Cine Cosmos", "LA LIBERTAD DOBLE", f"2026-10-0{d}", "21:00")
                    for d in range(1, 6)]
ok("el Cosmos repite de jueves a lunes: queda sólo la función de la guía",
   festival(grilla + cosmos_jue_a_lun),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla])

ok("la sala publica el programa de cortos con otro nombre, en el horario de la guía",
   festival(grilla + [sala("Cine Cosmos", "Cortos UBA", "2026-10-04", "16:00")]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla])

ok("un corto suelto del programa, en otro horario, también se va",
   festival(grilla + [sala("Cine Cosmos", "La hora de la siesta", "2026-10-05", "18:00")]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla])

ok("la sala pone una película del festival en otra fecha (CTBA, La hija cóndor)",
   festival(grilla + [sala("Sala Lugones", "La hija cóndor", "2026-09-30", "15:00", CTBA)]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla])

ok("la programación propia de la sala, en otro horario, queda",
   festival(grilla + [sala("Cine Cosmos", "Dos pianos", "2026-10-02", "15:00")]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla]
   + [("Cine Cosmos", "Dos pianos", "2026-10-02", "15:00")])

ok("fuera de las fechas o de las salas del festival no se toca nada",
   festival(grilla + [sala("Cine Cosmos", "La libertad doble", "2026-10-08", "21:00"),
                      sala("MALBA", "La libertad doble", "2026-10-02", "21:00")]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla]
   + [("Cine Cosmos", "La libertad doble", "2026-10-08", "21:00"),
      ("MALBA", "La libertad doble", "2026-10-02", "21:00")])

ok("la misma función con el ciclo del CTBA se va: queda la de la guía",
   festival(grilla + [sala("Sala Lugones", "Imperium", "2026-09-30", "14:00", CTBA)]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla])

# Idéntica a la de la guía, ciclo incluido: pasa, y la deduplicación final se
# queda con la primera, que es la manual.
ok("la copia exacta de una función de la guía pasa (la saca la dedupe final)",
   festival(grilla + [sala("Sala Lugones", "Imperium", "2026-09-30", "14:00", PAN)]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla]
   + [("Sala Lugones", "Imperium", "2026-09-30", "14:00")])

ok("un ciclo que sólo empieza parecido no es del festival",
   festival(grilla + [sala("Cine Cosmos", "Ficubano", "2026-10-03", "12:00", "FICUBANOS")]),
   [(m.cine, m.title, m.fecha, m.hora) for m in grilla]
   + [("Cine Cosmos", "Ficubano", "2026-10-03", "12:00")])

# Sobre las dicts de la cartelera publicada (title_es) funciona igual.
quedan, n = aplicar_festivales(
    [{"cine": "Cine Cosmos", "title_es": "La libertad doble", "fecha": "2026-10-03",
      "hora": "21:00", "ciclo": ""}], GRILLA)
ok("también sobre la cartelera publicada", (len(quedan), n), (0, 1))

if fallas:
    print(f"\n{fallas} FALLA(S)")
    sys.exit(1)
print("\nTODO OK")
