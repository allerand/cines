# Auditoría de la cartelera — lunes 9 de noviembre

## 🔴 Hay 8 cosas para mirar en 8 cines

Datos de hace 10 h · 33 cines · 3870 funciones publicadas.

## Para mirar esta semana

- **Centro Cultural Leopoldo Marechal** — lleva 1 día sin ninguna función (traía ~51 por día). Revisá su scraper.
- **Escuela Da Vinci** — lleva 9 días sin ninguna función (traía ~20 por día). Revisá su scraper.
- **Casa del Bicentenario** — lleva 2 días sin ninguna función (traía ~4 por día), y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.
- **Club Lucero** — lleva 10 días sin ninguna función (traía ~28 por día). Revisá su scraper.
- **Filo Cine** — hay funciones cuyo título son varias películas juntas (o una película más una charla): así no matchean contra la fuente ni contra Letterboxd y quedan sin director, año ni link — hay que desagregarlas en una fila por película (×2). Ejemplo: 'Atardecer en América + A través de la tierra'
- **Amorina** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Torneo de parejas · Truco'
- **Centro Cultural 25 de Mayo** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Semana de los Festivales de Cine de Málaga y San Sebastián en Buenos Aires – Mass 2026'
- **Sala Lugones** — hay horarios que no se pudieron parsear. Ejemplo: El tren fluvial: '??'

## Qué cambió desde la semana pasada

- **Centro Cultural Leopoldo Marechal** desapareció: 51 → 0 funciones.
- **Bellas Artes** desapareció: 3 → 0 funciones.
- **Casa del Bicentenario** desapareció: 1 → 0 funciones.
- **Cine Cosmos** bajó bastante: 24 → 8 funciones.
- **Cacodelphia** subió bastante: 18 → 41 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Cine Cosmos | 8 | 6 | ~24 |

Los otros 32 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Bellas Artes** lleva 2 días sin ninguna función (traía ~3 por día); entra y sale del cero seguido, puede que no haya programado.
- **Centro Cultural Borges**: dos títulos en el mismo horario ×4.
- **MALBA**: dos títulos en el mismo horario ×1.
- **Sala Lugones**: ticket_url inválido ×1.
- 18 funciones sin director: Centro Cultural 25 de Mayo (4/5), Centro Cultural Borges (14/25).
- 26 funciones sin link de Letterboxd: Centro Cultural 25 de Mayo (4/5), Centro Cultural Borges (16/25), Hasta Trilce (6/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
