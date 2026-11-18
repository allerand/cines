"""El chip "Otras" agrupa las salas de paso de los festivales: no es una sala
para la auditoría, y cada sala del grupo tiene dirección."""
import json
import re
from pathlib import Path

from scripts import audit

ROOT = Path(__file__).parent
html = (ROOT / "index.html").read_text(encoding="utf-8")

salas, _, direcciones = audit.leer_padron(ROOT)
assert "Otras" not in salas, "el chip Otras no puede contar como sala en el padrón"
assert "Espacio INCAA Morón" in salas

grupo = re.search(r"const SALAS_OTRAS = new Set\(\[(.*?)\]\)", html, re.S).group(1)
otras = re.findall(r"'([^']+)'", grupo)
assert len(otras) == 3, otras
for sala in otras:
    assert sala in direcciones, f"{sala} no tiene dirección"
    assert f'data-cine="{sala}"' not in html, f"{sala} no debe tener chip propio"
assert "'Territorio de Memoria Tres Ombúes',  // La Matanza" in html

registro = json.loads((ROOT / "data" / "festivales.json").read_text(encoding="utf-8"))["festivales"]
bain = next(f for f in registro if f["slug"] == "bain")
assert bain["gratis"] is True and (bain["desde"], bain["hasta"]) == ("2026-11-25", "2026-11-29")
for slug in ("bain", "mass", "rojo-sangre"):
    logo = next(f for f in registro if f["slug"] == slug)["logo"]
    assert (ROOT / logo).exists(), logo

print("ok: test_salas_otras")
