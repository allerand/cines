#!/usr/bin/env python3
"""
Test local del Museo del Cine Pablo Ducrós Hicken, sin red.

    python3 test_museo_cine.py

Las fixtures son el texto REAL de dos notas del museo (tests/fixtures/).

El modo de falla que arregla: el 11/9/2026 el museo publicó la programación en
una noticia titulada "Programacion del mes" —slug /noticias/programacion-del-mes,
sin el nombre del mes— y el descubrimiento, que exigía /noticias/<mes>-…, dejó
septiembre entero afuera de la cartelera. Con la nota ya en la mano aparecieron
otras tres: la ficha tenía que terminar en el paréntesis, la película metida en
el header después del "|" no se leía, y el mes se adivinaba con el primer nombre
de mes que apareciera en el texto.
"""
from datetime import date
from pathlib import Path

from scraper import (_museo_film_parts, _museocine_slug_month,
                     _parse_museocine_page)

FIX = Path(__file__).parent / "tests" / "fixtures"


def parsear(fixture: str, slug_month=None, hoy=date(2026, 9, 1)) -> list[dict]:
    return _parse_museocine_page(
        (FIX / fixture).read_text(encoding="utf-8"), slug_month, hoy)


def clave(e: dict) -> tuple:
    return (e["fecha"], e["hora"], e["title"])


# ---------------------------------------------------------------------------
# 1) La nota de septiembre de 2026, entera
# ---------------------------------------------------------------------------
sept = parsear("museo_septiembre_2026.txt")
assert [clave(e) for e in sept] == [
    ("2026-09-05", "16:00", "Las tres ratas"),
    ("2026-09-05", "18:00", "La noche cobra vida"),
    ("2026-09-06", "16:00", "Njangaan"),
    ("2026-09-06", "18:00", "Viento salvaje"),
    ("2026-09-12", "16:00", "Elvira Fernández vendedora de tienda"),
    ("2026-09-13", "16:00", "Deserto vértigo"),
    ("2026-09-13", "18:00", "El origen de las especies"),
], [clave(e) for e in sept]
print("✓ las 7 funciones de la nota de septiembre, sin mes en el slug")

# La coletilla después del paréntesis no puede comerse el título ni al director:
# "… (1942) en conversación con Iván Morales." salía entero como nombre de
# película, sin director y sin año.
elvira = sept[4]
assert elvira["director"] == "Manuel Romero", elvira
assert elvira["year"] == 1942, elvira
assert elvira["ciclo"] == "La llamada fatal", elvira
print("✓ la ficha con coletilla se parsea igual (título, director, año)")

# Película INLINE en el header, después del "|", y ciclo heredado de la
# cabecera de sección "Muestra especial: …" que no tiene horario propio.
assert sept[5]["director"] == "Rocío Barbenza" and sept[5]["year"] == 2025, sept[5]
assert sept[6]["director"] == "Ana Tiagx Vélez, Juliana Zuluaga y Analú Laferal", sept[6]
assert sept[5]["ciclo"] == sept[6]["ciclo"] == "Arder en la frontera", (sept[5], sept[6])
print("✓ la película metida en el header sale, con el ciclo de la muestra")

# Lo que el portal cuelga abajo ("Últimas noticias": Deportes, Cultos…) no es
# programación: si se cuela, aparecen funciones fantasma.
assert not any("Fórmula" in e["title"] or "Macri" in e["title"] for e in sept)
print("✓ el bloque de Últimas noticias del portal no genera funciones")

# ---------------------------------------------------------------------------
# 2) Ciclo de cortos: una fila por corto
# ---------------------------------------------------------------------------
agosto = parsear("museo_agosto_2026_cortos.txt")
cortos = [e for e in agosto if e["hora"] == "16:00"]
assert [e["title"] for e in cortos] == [
    "El corazón de la lengua", "La intérprete", "Lauchita", "Luz mala",
], [e["title"] for e in cortos]
assert [e["director"] for e in cortos] == [
    "Yanina Gruden", "Sofía Rovaletti", "Emi Castañeda",
    "Carmen Lanzi Giannoni y Martina Ocampo",
], [e["director"] for e in cortos]
assert all(e["ciclo"].startswith("Futuras") for e in cortos), cortos
assert all(e["fecha"] == "2026-08-16" for e in cortos), cortos
print("✓ el ciclo de cortos se desagrega: una fila por corto, con su director")

# La función que sigue no se contagia del programa de cortos.
otras = [e for e in agosto if e["hora"] == "18:00"]
assert [e["title"] for e in otras] == ["Mis seis presidiarios"], otras
print("✓ la función siguiente sigue siendo una sola fila")

# ---------------------------------------------------------------------------
# 3) De qué mes es la nota cuando el slug no lo dice
# ---------------------------------------------------------------------------
# Los headers mandan sobre cualquier mes suelto de una sinopsis.
CON_SINOPSIS_TRAMPOSA = """Viernes 11 de Septiembre de 2026
Programacion del mes
Les acercamos la programación de nuestro auditorio del 1 al 15 de septiembre.
Sábado 5 de septiembre a las 16 h | Cine argentino en video
Las tres ratas de Carlos Schlieper (1946)
La película se estrenó en agosto y fue un éxito de agosto a diciembre.
"""
ev = _parse_museocine_page(CON_SINOPSIS_TRAMPOSA, None, date(2026, 9, 1))
assert [e["fecha"] for e in ev] == ["2026-09-05"], ev
print("✓ una sinopsis que nombra otro mes no corre las fechas")

# Sin mes en los headers, lo dice la bajada ("del 1 al 15 de septiembre").
SIN_MES_EN_HEADER = """Viernes 11 de Septiembre de 2026
Programacion del mes
Les acercamos la programación de nuestro auditorio del 1 al 15 de septiembre.
Sábado 5 a las 16 h | Cine argentino en video
Las tres ratas de Carlos Schlieper (1946)
"""
ev = _parse_museocine_page(SIN_MES_EN_HEADER, None, date(2026, 9, 1))
assert [e["fecha"] for e in ev] == ["2026-09-05"], ev
print("✓ sin mes en el header, el mes sale de la bajada")

# ---------------------------------------------------------------------------
# 4) La nota de diciembre que programa enero
# ---------------------------------------------------------------------------
DICIEMBRE = """Lunes 22 de Diciembre de 2026
Programacion del mes
Les acercamos la programación de nuestro auditorio del 3 al 31 de enero.
Sábado 3 de enero a las 16 h | Cineclub infantil
El circo de Charles Chaplin (1928)
"""
ev = _parse_museocine_page(DICIEMBRE, None, date(2026, 12, 22))
assert [e["fecha"] for e in ev] == ["2027-01-03"], ev
print("✓ la nota de diciembre que programa enero cae en el año siguiente")

# Y una nota vieja NO se empuja al futuro: tiene que quedar en el pasado para
# que la ventana de fechas la descarte.
VIEJA = """Miércoles 01 de Julio de 2026
Julio en el auditorio
Sábado 4 de julio a las 16 h | Pioneras
La sonriente Madame Beudet de Germaine Dulac (1923)
"""
ev = _parse_museocine_page(VIEJA, 7, date(2026, 9, 13))
assert [e["fecha"] for e in ev] == ["2026-07-04"], ev
print("✓ una nota vieja se queda en el pasado y la descarta la ventana")

# ---------------------------------------------------------------------------
# 5) El slug: pista para el mes, nunca filtro
# ---------------------------------------------------------------------------
BASE = "https://buenosaires.gob.ar/gcaba_historico/noticias/"
assert _museocine_slug_month(BASE + "agosto-en-el-museo-del-cine-0") == 8
assert _museocine_slug_month(BASE + "julio-en-el-auditorio") == 7
assert _museocine_slug_month(BASE + "programacion-del-mes") is None
print("✓ el mes del slug se lee si está, y su ausencia no descarta la nota")

# ---------------------------------------------------------------------------
# 6) La ficha suelta
# ---------------------------------------------------------------------------
assert _museo_film_parts("El circo de Charles Chaplin (1928)") == \
    ("El circo", "Charles Chaplin", 1928, "")
assert _museo_film_parts(
    "Elvira Fernández vendedora de tienda de Manuel Romero (1942) en conversación con Iván Morales."
)[:3] == ("Elvira Fernández vendedora de tienda", "Manuel Romero", 1942)
# Un paréntesis sin año es parte de la sinopsis, no una ficha.
assert _museo_film_parts("Mercedes, la hermana mayor (Mecha Ortíz) toma el rol protector.") is None
print("✓ la ficha necesita un año adentro del paréntesis")

print("✓ OK")
