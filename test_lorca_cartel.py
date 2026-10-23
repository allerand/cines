#!/usr/bin/env python3
"""
Test de la lectura del cartel del Cine Lorca, sin red y sin tesseract:

    python3 test_lorca_cartel.py

Los dos fixtures son salidas TSV reales de tesseract sobre el cartel del
24/09-30/09 de 2026: una lectura buena y una a la que se le perdió la fila del
medio del cartel. La segunda es la que importa: cuando una fila se pierde, sus
horarios se le cuelgan a la película de arriba —La invitación a las 14.05 pasa
a ser una función de Pepita la pistolera— y eso no se ve por ningún lado. Por
eso la lectura se descarta entera.
"""
import csv
from datetime import date
from pathlib import Path

from scraper import (_lorca_carteles, _lorca_dias, _lorca_es_titulo,
                     _lorca_lectura_sana, _lorca_leer_partes, _lorca_leer_tsv,
                     _lorca_render, _lorca_titulo_conocido)

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
HOY = date(2026, 9, 28)      # el lunes de esa semana


def leer(nombre):
    with open(FIXTURES / f"lorca_cartel_{nombre}.tsv", encoding="utf-8") as fh:
        return _lorca_leer_tsv(list(csv.DictReader(fh, delimiter="\t",
                                                   quoting=csv.QUOTE_NONE)))


# --- La lectura buena: el cartel entero --------------------------------------
ok = leer("ok")
assert ok["rango"] == (24, 9, 30, 9) and ok["anio"] == 2026
assert ok["huerfanas"] == 0
assert ok["grilla"] == {
    "PEPITA LA PISTOLERA":     ["20:10", "22:20"],
    "UNA QUINTA EN PORTUGAL":  ["14:00", "18:15"],
    "LA INVITACION":           ["14:05"],
    "SU PROPIO INFIERNO":      ["20:20"],
    "TRES ADIOSES":            ["16:05", "17:50"],
    "EL CORAZON DE LA BESTIA": ["16:00", "22:10"],
}, ok["grilla"]
print("✓ el cartel se lee entero: seis películas, diez funciones y el rango de la semana")

assert _lorca_lectura_sana(ok, HOY) == (date(2026, 9, 24), date(2026, 9, 30))
print("✓ la lectura buena pasa los controles y da la franja de jueves a miércoles")


# --- La lectura a la que se le perdió una fila -------------------------------
mala = leer("fila_perdida")
assert mala["huerfanas"] == 2
# Las dos funciones de la fila perdida quedaron sin título propio…
assert "LA INVITACION" not in mala["grilla"] and "SU PROPIO INFIERNO" not in mala["grilla"]
# …y no se le colgaron a la película de arriba.
assert "14:05" not in mala["grilla"]["PEPITA LA PISTOLERA"], mala["grilla"]
assert _lorca_lectura_sana(mala, HOY) is None
print("✓ si se pierde una fila, la lectura entera se descarta (no se reparten sus horarios)")


# --- Los controles sobre la lectura ------------------------------------------
def variar(**cambios):
    return {**ok, **cambios}


assert _lorca_lectura_sana(variar(rango=None), HOY) is None
assert _lorca_lectura_sana(variar(conf_horas=42.0), HOY) is None
assert _lorca_lectura_sana(variar(conf_titulos=20.0), HOY) is None
assert _lorca_lectura_sana(variar(grilla={"UNA SOLA": ["20:00"]}), HOY) is None
assert _lorca_lectura_sana(variar(grilla={t: ["20:00"] * 7 for t in ("A B C D", "E F G H")}), HOY) is None
print("✓ sin rango, con poca confianza, con una sola película o con siete horarios: no se publica")

# Los títulos aguantan menos confianza que los horarios: van en negrita sobre
# gris y el OCR les baja la nota aunque los lea bien.
assert _lorca_lectura_sana(variar(conf_titulos=55.0), HOY) is not None

# El cartel de la semana pasada, todavía colgado, no se publica.
assert _lorca_lectura_sana(ok, date(2026, 10, 6)) is None
# Y el de la semana que viene, publicado el miércoles, sí.
assert _lorca_lectura_sana(ok, date(2026, 9, 22)) == (date(2026, 9, 24), date(2026, 9, 30))
print("✓ un cartel vencido no entra; uno que arranca en unos días, sí")

# Un rango que no es una semana (un error de lectura en los números).
assert _lorca_lectura_sana(variar(rango=(24, 9, 30, 12)), HOY) is None
print("✓ un rango que no parece una semana se descarta")


# --- Qué es un título y qué no -----------------------------------------------
assert _lorca_es_titulo("EL CORAZON DE LA BESTIA")
assert _lorca_es_titulo('"TRES ADIOSES"')
assert not _lorca_es_titulo("SALA 2")
assert not _lorca_es_titulo("Duración: 103 MIN - R-17 - ESP")
assert not _lorca_es_titulo("PRECIOS DE LAS ENTRADAS:")
assert not _lorca_es_titulo("-JUEVES A DOMINGOS Y FERIADOS: $10.000")
assert not _lorca_es_titulo("VÁLIDA DESDE EL")
print("✓ las etiquetas del cartel (sala, duración, precios) no son películas")


# --- Cómo se escriben los títulos --------------------------------------------
conocidos = ["El Corazon De La Bestia"] * 4 + ["El corazón de la bestia"] * 2 + \
            ["Pepita, La Pistolera", "Pepita la pistolera", "Tres adioses"]
assert _lorca_titulo_conocido("EL CORAZON DE LA BESTIA", conocidos) == "El corazón de la bestia"
assert _lorca_titulo_conocido("PEPITA LA PISTOLERA", conocidos) == "Pepita la pistolera"
assert _lorca_titulo_conocido("TRES ADIOSES", conocidos) == "Tres adioses"
# Una que no está en la cartelera queda como la escribe el cartel.
assert _lorca_titulo_conocido("UNA PELICULA NUEVA", conocidos) == "UNA PELICULA NUEVA"
assert _lorca_titulo_conocido("TRES ADIOSES", None) == "TRES ADIOSES"
print("✓ el título se escribe como el resto de la cartelera, en su forma más natural")


# --- La imagen del cartel se pide sin los filtros de la web ------------------
HTML = ('<img src="https://static.wixstatic.com/media/29f330_41e4cf~mv2.jpg/v1/'
        'crop/x_0,y_2,w_745,h_523/fill/w_596,h_418,al_c,q_80,usm_0.66_1.00_0.01,'
        'enc_avif,quality_auto/HS8Uv.jpg">')
carteles = _lorca_carteles(HTML)
assert len(carteles) == 1 and carteles[0][0] == "29f330_41e4cf~mv2.jpg"
url = _lorca_render(*carteles[0], 1490)
assert url == ("https://static.wixstatic.com/media/29f330_41e4cf~mv2.jpg/v1/fill/"
               "w_1490,h_1045,al_c,q_90,enc_auto/cartel.jpg"), url
print("✓ la imagen se pide grande y sin compresión ni enfoque, que es lo que confunde al OCR")


# --- El cartel del 22 al 28/10/2026: títulos subrayados, días alternados -----
# Ninguna lectura del lector de posiciones pasaba los controles (el subrayado
# le tapa los títulos) y el Lorca salió de La Nación, que el jueves 22 daba
# Digger donde el cartel decía Los otros. Los fixtures son la salida TSV real
# de cada columna del cartel, ya sin rayas: una buena (1600 px, psm 6) y una a
# la que se le escapó el título de Digger (1490 px, psm 11).
def leer_columnas(nombre):
    partes = []
    for i in range(3):
        with open(FIXTURES / f"lorca_columnas_{nombre}_{i}.tsv", encoding="utf-8") as fh:
            partes.append(list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)))
    return _lorca_leer_partes(partes)


JUEVES = date(2026, 10, 22)
nuevo = leer_columnas("ok")
assert nuevo["rango"] == (22, 10, 28, 10) and nuevo["huerfanas"] == 0
assert nuevo["grilla"] == {
    "LOS OTROS":                ["22:00"],
    "LA VIDA ES ASI":           ["14:00", "19:50"],
    "UNA QUINTA EN PORTUGAL":   ["13:55", "16:10"],
    "DIGGER":                   ["22:00"],
    "QUIERO TU SEXO":           ["22:10"],
    "LA CASA":                  ["16:00"],
    "TIEMPOS DE ILUSION":       ["20:00"],
    "BUENAS VIBRACIONES":       ["18:15"],
    "QUE DIOS PERDONA A TODOS": ["18:00"],
}, nuevo["grilla"]
# Los otros jueves, sábado, lunes y miércoles; Digger viernes, domingo y martes.
assert nuevo["dias"] == {"LOS OTROS": (0, 2, 3, 5), "DIGGER": (1, 4, 6)}, nuevo["dias"]
assert _lorca_lectura_sana(nuevo, JUEVES) == (date(2026, 10, 22), date(2026, 10, 28))
print("✓ el cartel subrayado se lee por columnas: nueve películas y quién va qué día a las 22.00")

perdido = leer_columnas("titulo_perdido")
assert "DIGGER" not in perdido["grilla"]
# El 22.00 y los días de Digger quedaron sin película, y no pasaron a la de
# arriba: Una quinta en Portugal sigue con sus dos horarios y sin días.
assert perdido["huerfanas"] == 2
assert perdido["grilla"]["UNA OUINTA EN PORTUGAL"] == ["13:55", "16:10"]
assert "UNA OUINTA EN PORTUGAL" not in perdido["dias"]
assert _lorca_lectura_sana(perdido, JUEVES) is None
print("✓ si se pierde un título, sus días y su horario no se le cuelgan a la película de arriba")

# Sin las aclaraciones, Los otros y Digger chocan a las 22.00 en la sala 1.
assert _lorca_lectura_sana({**nuevo, "dias": {}}, JUEVES) is None
# El lector de posiciones no sabe a qué película va cada aclaración: si el
# cartel trae alguna, su lectura no se publica.
assert _lorca_lectura_sana({**ok, "dias_sin_asignar": True}, HOY) is None
print("✓ dos películas a la misma hora en la misma sala no se publican")

assert _lorca_dias("(jueves, sábado, lunes, miércoles)") == (0, 2, 3, 5)
assert _lorca_dias("(viernes, Domingo, martes)") == (1, 4, 6)
assert _lorca_dias("(LUNES, MARTES Y") is None                 # los precios del costado
assert _lorca_dias("-JUEVES A DOMINGOS Y FERIADOS: $10.000") is None
assert _lorca_dias('"LOS OTROS"') is None
print("✓ las aclaraciones de días se leen, y los precios del costado no se confunden con ellas")

# El OCR cambia una letra o pega una de más en la punta; nada más que eso.
conocidos = ["Una quinta en Portugal", "La vida es así", "El agente secreto 2", "La caza"]
assert _lorca_titulo_conocido("UNA OUINTA EN PORTUGAL", conocidos) == "Una quinta en Portugal"
assert _lorca_titulo_conocido("NLA VIDA ES ASI", conocidos) == "La vida es así"
assert _lorca_titulo_conocido("EL AGENTE SECRETO", conocidos) == "EL AGENTE SECRETO"
assert _lorca_titulo_conocido("LA CASA", conocidos) == "LA CASA"
print("✓ un título con una letra mal leída se reconoce; uno al que le falta algo o muy corto, no")

print("\nTodo OK")
