# Auditoría de la cartelera — lunes 14 de septiembre

## 🔴 Hay 2 cosas para mirar en 2 cines

Datos de hace 5 h · 33 cines · 2444 funciones publicadas.

## Para mirar esta semana

- **Archivo General de la Nación** — lleva 14 días sin ninguna función, pero la fuente publica 2 funciones futuras en la landing. El scraper se rompió.
- **Casa del Bicentenario** — lleva 14 días sin ninguna función, y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.

## Qué cambió desde la semana pasada

- **Amorina** desapareció: 2 → 0 funciones.
- **Cine York** bajó bastante: 57 → 11 funciones.
- **Cinépolis Recoleta** subió bastante: 22 → 48 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Cine York | 11 | 11 | ~35 |

Los otros 32 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Museo del Cine** lleva 1 día sin ninguna función (traía ~2 por día); entra y sale del cero seguido, puede que no haya programado.
- **CEA** lleva 1 día sin ninguna función (traía ~4 por día); entra y sale del cero seguido, puede que no haya programado.
- **Centro Cultural Borges**: director que no es un nombre ×6.
- **Sala Lugones**: ticket_url inválido ×5.
- **Cacodelphia**: dos títulos en el mismo horario ×1.
- 6 funciones sin director: Centro Cultural Recoleta (5/5), Lumiton (1/1).
- 10 funciones sin link de Letterboxd: Centro Cultural de la Cooperación (3/3), Hasta Trilce (6/6), Lumiton (1/1).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
