# Auditoría de la cartelera — lunes 2 de noviembre

## 🔴 Hay 5 cosas para mirar en 5 cines

Datos de hace 10 h · 36 cines · 3652 funciones publicadas.

## Para mirar esta semana

- **Club Lucero** — lleva 3 días sin ninguna función (traía ~28 por día). Revisá su scraper.
- **Escuela Da Vinci** — lleva 2 días sin ninguna función (traía ~20 por día). Revisá su scraper.
- **Filo Cine** — hay funciones cuyo título son varias películas juntas (o una película más una charla): así no matchean contra la fuente ni contra Letterboxd y quedan sin director, año ni link — hay que desagregarlas en una fila por película (×2). Ejemplo: 'Rabiola + Portuñol'
- **Centro Cultural 25 de Mayo** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Semana de los Festivales de Cine de Málaga y San Sebastián en Buenos Aires – Mass 2026'
- **Sala Lugones** — hay horarios que no se pudieron parsear. Ejemplo: El tren fluvial: '??'

## Qué cambió desde la semana pasada

- **Cineclub Farus** desapareció: 2 → 0 funciones.
- **Casa del Bicentenario** bajó bastante: 14 → 1 funciones.
- **Centro Cultural Leopoldo Marechal** volvió a la cartelera: 0 → 51 funciones.
- **Cinépolis Houssay** volvió a la cartelera: 0 → 17 funciones.
- **Sala Lugones** subió bastante: 30 → 68 funciones.
- **Cine York** subió bastante: 18 → 37 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Casa del Bicentenario | 1 | 1 | ~10 |

Los otros 35 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Centro Cultural Leopoldo Marechal**: ticket_url inválido ×51.
- **Sala Lugones**: ticket_url inválido ×13.
- **Centro Cultural Borges**: dos títulos en el mismo horario ×3.
- **Centro Cultural Leopoldo Marechal**: dos títulos en el mismo horario ×3.
- 23 funciones sin director: Centro Cultural 25 de Mayo (3/5), Centro Cultural Borges (15/27), Filo Cine (5/8).
- 32 funciones sin link de Letterboxd: Casa del Bicentenario (1/1), Centro Cultural Borges (18/27), Centro Cultural de la Cooperación (2/3), Filo Cine (5/8), Hasta Trilce (6/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
