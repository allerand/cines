# Auditoría de la cartelera — domingo 15 de noviembre

## 🔴 Hay 7 cosas para mirar en 7 cines

Datos de hace 1 h · 33 cines · 4396 funciones publicadas.

## Para mirar esta semana

- **Centro Cultural Borges** — publica 16 función(es) pero no scrapeó ninguna en la última corrida: la API no contesta; se publica el caché de la última corrida buena. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **CCK** — publica 10 función(es) pero no scrapeó ninguna en la última corrida: no se pudo leer palaciolibertad.gob.ar/cine/. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Bellas Artes** — publica 3 función(es) pero no scrapeó ninguna en la última corrida: la fuente no contestó. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Centro Cultural Leopoldo Marechal** — lleva 7 días sin ninguna función (traía ~51 por día). Revisá su scraper.
- **Casa del Bicentenario** — lleva 8 días sin ninguna función (traía ~1 por día), y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.
- **Sala Lugones** — hay horarios que no se pudieron parsear (×4). Ejemplo: Andrzej Wajda bis: '??'
- **Filo Cine** — hay funciones cuyo título son varias películas juntas (o una película más una charla): así no matchean contra la fuente ni contra Letterboxd y quedan sin director, año ni link — hay que desagregarlas en una fila por película. Ejemplo: 'La pasarela + El invisible sustento de la frontera'

## Qué cambió desde la semana pasada

- **Centro Cultural Leopoldo Marechal** desapareció: 21 → 0 funciones.
- **Centro Cultural 25 de Mayo** desapareció: 5 → 0 funciones.
- **Centro Cultural de la Cooperación** desapareció: 2 → 0 funciones.
- **Sala Lugones** bajó bastante: 54 → 18 funciones.
- **Cineclub Farus** volvió a la cartelera: 0 → 5 funciones.
- **Bellas Artes** volvió a la cartelera: 0 → 3 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Sala Lugones | 18 | 11 | ~57 |

Los otros 32 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Cine Cosmos** publica 32 función(es), pero su scraper avisa: cosmos.uba.ar no contesta (HTTP Error 503: Service Temporarily Unavailable); la cartelera sale de Instagram (@cinecosmos.uba).
- **Centro Cultural de la Cooperación** lleva 2 días sin ninguna función (traía ~2 por día); entra y sale del cero seguido, puede que no haya programado.
- **Sala Lugones**: dos títulos en el mismo horario ×6.
- **Sala Lugones**: ticket_url inválido ×4.
- **Centro Cultural Borges**: dos títulos en el mismo horario ×3.
- **Sala Lúcida**: director que no es un nombre ×1.
- **Cacodelphia**: dos títulos en el mismo horario ×1.
- 12 funciones sin director: Sala Lugones (12/18).
- 18 funciones sin link de Letterboxd: Hasta Trilce (6/6), Sala Lugones (12/18).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
