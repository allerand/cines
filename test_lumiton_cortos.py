#!/usr/bin/env python3
"""
Test local del desagregado de los programas de cortos de Lumiton
(_lumiton_cortos), sin red.

    python3 test_lumiton_cortos.py

El modo de falla que arregla: la Convocatoria de Cortos salía como UNA fila
llamada "Convocatoria de Cortos: Programa I", sin director y sin año — o sea,
diez cortos que no se podían encontrar buscando ni la película ni a quien la
dirigió. Las trampas del HTML real están todas acá: fichas con paréntesis
adentro del nombre del director, paréntesis que la página se olvida de cerrar,
"Arg" sin punto, y párrafos en <strong> que NO son cortos (la bajada del
programa y el bloque de la sala).
"""
from bs4 import BeautifulSoup

from scraper import _lumiton_cortos


def parsear(html: str) -> list[dict]:
    return _lumiton_cortos(BeautifulSoup(
        f'<div class="prose">{html}</div>', "html.parser"))


PROGRAMA = """
<p>Primera jornada dedicada a los cortometrajes seleccionados.</p>
<p><strong>La continuidad de los patios</strong> (Dir. Luciano Scarcia | Arg. / 2025 / 2’ / +13)<br/>Una interpretación del cuento de Cortázar.</p>
<p><strong>Steve Buscemi</strong> (Dir. Lucila Lopatin y Martina Vogelfang | Arg. / 2026 / 19′ / ATP)<br/>Dafne inventa que adoptó un cachorro.</p>
<p><strong>Arquitectura de un Instante</strong> (Dir. Lucas De Benedetti | Arg., Uruguay / 2026 / 20’ / ATP)<br/>Soledad y Javier se reconocen.</p>
<p><strong>Miss Mix</strong> (Dir. Vir Zone (Virginia Tassone) | Arg. / 2024 / 2’ / ATP Miss Mix descubre una perilla en 1998 que baja el volumen.</p>
<p><strong>Otecito, el osito del tecito</strong> (Dir. Nathaniel Pacheco | Arg / 2025 / 12’ / ATP)<br/>Hibis, una adolescente.</p>
<p><strong>en Cine York</strong> (Juan Bautista Alberdi 895, Olivos) Entrada no arancelada.</p>
"""

cortos = parsear(PROGRAMA)
assert [c["title"] for c in cortos] == [
    "La continuidad de los patios", "Steve Buscemi",
    "Arquitectura de un Instante", "Miss Mix", "Otecito, el osito del tecito",
], cortos
assert [c["director"] for c in cortos] == [
    "Luciano Scarcia", "Lucila Lopatin y Martina Vogelfang",
    "Lucas De Benedetti", "Vir Zone (Virginia Tassone)", "Nathaniel Pacheco",
], [c["director"] for c in cortos]
assert [c["year"] for c in cortos] == [2025, 2026, 2026, 2024, 2025], cortos
assert [c["duration"] for c in cortos] == [2, 19, 20, 2, 12], cortos
assert [c["country"] for c in cortos] == [
    "Arg", "Arg", "Arg., Uruguay", "Arg", "Arg"], cortos
print("✓ los 5 cortos, con director/año/duración; la sala y la bajada no cuentan")

# El año y la duración salen de la ficha, no de la sinopsis: "Miss Mix" nombra
# 1998 y se quedó igual con 2024. Sin el corte por barras, una sinopsis larga
# le pisa el año a la película.
assert cortos[3]["year"] == 2024

# Dos cortos en el MISMO <p>, separados por <br><br>: así publicó Lumiton el
# Programa III, y "Hipótesis sobre mis dos huevos" no salió en la web del
# 12/9/2026 porque sólo se miraba el primer <strong> de cada párrafo.
JUNTOS = """
<p>Tercera jornada dedicada a los cortometrajes seleccionados.</p>
<p><strong>Duende</strong> (Dir. Ornella Berardi y Luiza Loures | Arg. / 2025 / 5&#8242; / ATP)<br/>Floriana, 22, sigue a una niña de pollera roja.<br/><br/><strong>Hipótesis sobre mis dos huevos</strong> (Dir. Theo Fernandez | Arg. / 2026 / 15’ / +18)<br/>Un alter ego del director elabora una hipótesis.</p>
<p><strong>Elogio a los fantasmas</strong> (Dir. Facundo Rodriguez Alonso | Arg. / 2025 / 17’ / +16)<br/>La búsqueda del fantasma de su madre.</p>
<p><strong>en Cine York</strong> (Juan Bautista Alberdi 895, Olivos) Entrada no arancelada.</p>
"""

juntos = parsear(JUNTOS)
assert [c["title"] for c in juntos] == [
    "Duende", "Hipótesis sobre mis dos huevos", "Elogio a los fantasmas",
], juntos
assert [c["director"] for c in juntos] == [
    "Ornella Berardi y Luiza Loures", "Theo Fernandez", "Facundo Rodriguez Alonso",
], [c["director"] for c in juntos]
# El año y la duración son los de CADA ficha: sin cortar en el título siguiente,
# el segundo corto se comía los datos del primero.
assert [c["year"] for c in juntos] == [2025, 2026, 2025], juntos
assert [c["duration"] for c in juntos] == [5, 15, 17], juntos
print("✓ dos cortos en un mismo párrafo salen los dos, con sus propios datos")

# Una película sola NO es un programa: la ficha normal de un evento la parsea
# fetch_lumiton_evento_meta con los <b>Dirección</b>, y desagregarla acá
# duplicaría la función.
assert parsear(
    '<p><strong>Hijo Mayor</strong> (Dir. Cecilia Kang | Arg. / 2025 / 118’ / +13)</p>'
) == []
print("✓ una sola ficha no se toma por programa de cortos")

# Un evento sin fichas queda intacto.
assert parsear("<p>Charla abierta con el equipo.</p>") == []
print("✓ un evento sin fichas devuelve []")

# El nombre del programa va de ciclo, y llega title-caseado desde acá: el
# title-case de run.py le baja el numeral romano ("PROGRAMA II" → "Programa Ii").
from scraper import _lumiton_ciclo

assert _lumiton_ciclo("CONVOCATORIA DE CORTOS: PROGRAMA II") == \
    "Convocatoria de Cortos: Programa II"
assert _lumiton_ciclo("CONVOCATORIA DE CORTOS: PROGRAMA I") == \
    "Convocatoria de Cortos: Programa I"
assert _lumiton_ciclo("Un ciclo ya escrito bien") == "Un ciclo ya escrito bien"
print("✓ el ciclo conserva el numeral romano")

print("✓ OK")
