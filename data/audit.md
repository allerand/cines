# Auditoría de la cartelera — lunes 28 de septiembre

## 🔴 Hay 4 cosas para mirar en 4 cines

Datos de hace 9 h · 31 cines · 2083 funciones publicadas.

## Para mirar esta semana

- **CCK** — lleva 2 días sin ninguna función (traía ~2 por día), y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.
- **Biblioteca Nacional** — lleva 6 días sin ninguna función (traía ~1 por día), pero la fuente publica 1 ítems en la listing. El scraper se rompió.
- **MALBA** — lleva 1 día sin ninguna función (traía ~12 por día), pero la fuente publica 9 ítems en la listing. El scraper se rompió.
- **Casa del Bicentenario** — lleva 14 días sin ninguna función, y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.

## Qué cambió desde la semana pasada

- **MALBA** desapareció: 12 → 0 funciones.
- **Arthaus** desapareció: 3 → 0 funciones.
- **Centro Cultural Recoleta** desapareció: 3 → 0 funciones.
- **CCK** desapareció: 1 → 0 funciones.
- **Biblioteca Nacional** desapareció: 1 → 0 funciones.
- **FADU** volvió a la cartelera: 0 → 9 funciones.
- **Amorina** volvió a la cartelera: 0 → 4 funciones.
- **Cacodelphia** subió bastante: 24 → 132 funciones.
- …y 3 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Arthaus** lleva 1 día sin ninguna función (traía ~3 por día); entra y sale del cero seguido, puede que no haya programado.
- **CEA** lleva 1 día sin ninguna función (traía ~2 por día); entra y sale del cero seguido, puede que no haya programado.
- **Centro Cultural Recoleta** lleva 1 día sin ninguna función (traía ~3 por día); entra y sale del cero seguido, puede que no haya programado.
- **Sala Lugones**: ticket_url inválido ×7.
- **Centro Cultural Borges**: director que no es un nombre ×2.
- 4 funciones sin director: Centro Cultural 25 de Mayo (4/5).
- 11 funciones sin link de Letterboxd: Centro Cultural 25 de Mayo (4/5), Centro Cultural de la Cooperación (1/1), Hasta Trilce (6/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
