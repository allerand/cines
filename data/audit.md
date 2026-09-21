# Auditoría de la cartelera — lunes 21 de septiembre

## 🔴 Hay 4 cosas para mirar en 4 cines

Datos de hace 9 h · 34 cines · 1745 funciones publicadas.

## Para mirar esta semana

- **Archivo General de la Nación** — lleva 14 días sin ninguna función, pero la fuente publica 1 funciones futuras en la landing. El scraper se rompió.
- **Museo del Cine** — lleva 8 días sin ninguna función (traía ~2 por día). Revisá su scraper.
- **CEA** — lleva 3 días sin ninguna función (traía ~2 por día). Revisá su scraper.
- **Casa del Bicentenario** — lleva 14 días sin ninguna función, y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.

## Qué cambió desde la semana pasada

- **Cineclub Farus** volvió a la cartelera: 0 → 1 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| CCK | 1 | 1 | ~5 |

Los otros 33 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Centro Cultural Borges**: director que no es un nombre ×3.
- **Cine York**: dos títulos en el mismo horario ×1.
- 5 funciones sin director: Centro Cultural Recoleta (3/3), Lumiton (2/2).
- 10 funciones sin link de Letterboxd: Centro Cultural de la Cooperación (2/2), Hasta Trilce (6/6), Lumiton (2/2).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
