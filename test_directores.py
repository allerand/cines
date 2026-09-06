#!/usr/bin/env python3
"""
Test local de los dos parsers de director que publicaban media sinopsis en la
columna DIRECTOR, sin red.

    python3 test_directores.py

Los dos casos son el mismo error visto desde dos webs distintas: el nombre del
director venía pegado a otra cosa y el corte se hacía por el final de la línea,
así que se llevaba todo. Da vergüenza en la cartelera y además rompe el
enrichment, que busca en Letterboxd por director.
"""
from datetime import date, timedelta

from scraper import _ccd_meta, _parse_cc25_detail

# --- Centro Cultural de la Cooperación -------------------------------------
# En el cuerpo cada campo va en su propio párrafo.
CUERPO = """Cine
Hornos sin fronteras
Miércoles 16, 23 y 30 de Septiembre 20:00
Dirección: John Dickinson
Hornos sin fronteras retrata a esta agrupación solidaria y federal de ceramistas.
Duración: 52 minutos"""
assert _ccd_meta(CUERPO, "Hornos sin fronteras") == ("John Dickinson", 52)
print("✓ CCC: del cuerpo salen el director y la duración")

# La meta-descripción del Drupal pega los párrafos sin separador, y encima se
# corta antes de la duración. Es el respaldo: el título alcanza para cortar.
META = ("Dirección: John Dickinson Hornos sin fronteras retrata a esta "
        "agrupación solidaria y federal de ceramistas.")
assert _ccd_meta(META, "Hornos sin fronteras") == ("John Dickinson", None)
print("✓ CCC: en la meta-descripción, el título corta la sinopsis")

# Sin título que sirva de corte no se inventa nada: mejor de más que de menos,
# porque un director vacío es peor que uno largo.
assert _ccd_meta("Dirección: Jean-Pierre Dardenne y Luc Dardenne", "") == (
    "Jean-Pierre Dardenne y Luc Dardenne", None)
print("✓ CCC: un crédito de dos directores no se corta")


# --- Centro Cultural 25 de Mayo --------------------------------------------
# El H1 encadena subtítulos con guiones largos: "TÍTULO – de DIRECTOR – CICLO".
def cc25(h1: str) -> list:
    hoy = date.today()
    cuerpo = (f"{h1}\nCATEGORÍA Cine\n"
              f"FECHA {hoy.day:02d} {'ene feb mar abr may jun jul ago sep oct nov dic'.split()[hoy.month - 1]} "
              f"{hoy.year}\nHORA 20:00\n")
    return _parse_cc25_detail(h1, cuerpo, "https://cc25.org/eventos/x/",
                              hoy, hoy + timedelta(weeks=6))


s = cc25("LA IMAGEN SANTA – de Pablo Montllau – Homenaje. 30 años del fallecimiento de Gilda")
assert s and s[0].director == "Pablo Montllau", s and s[0].director
assert s[0].title == "LA IMAGEN SANTA", s[0].title
print("✓ CC25: el subtítulo del ciclo no se cuela en el director")

# Sin subtítulo el director sigue llegando entero hasta el final del H1...
s = cc25("EL SUR – de Víctor Erice")
assert s and s[0].director == "Víctor Erice", s and s[0].director
# ...y un guión ASCII adentro de un nombre compuesto no corta nada.
s = cc25("MADRES JÓVENES – de Jean-Pierre Dardenne y Luc Dardenne")
assert s and s[0].director == "Jean-Pierre Dardenne y Luc Dardenne", s[0].director
print("✓ CC25: los nombres compuestos sobreviven al corte")

print("✓ OK")
