# Auditoría de la cartelera — lunes 19 de octubre

## 🔴 Hay 4 cosas para mirar en 4 cines

Datos de hace 9 h · 34 cines · 3135 funciones publicadas.

## Para mirar esta semana

- **Biblioteca Nacional** — lleva 14 días sin ninguna función, pero la fuente publica 1 ítems en la listing. El scraper se rompió.
- **Casa del Bicentenario** — lleva 14 días sin ninguna función, y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.
- **FADU** — lleva 12 días sin ninguna función (traía ~2 por día). Revisá su scraper.
- **Sala Lugones** — hay horarios que no se pudieron parsear (×2). Ejemplo: Cinema Kabuki: '??'

## Qué cambió desde la semana pasada

- **Centro Cultural de la Cooperación** desapareció: 3 → 0 funciones.
- **Museo del Cine** desapareció: 2 → 0 funciones.
- **Museo Moderno** volvió a la cartelera: 0 → 2 funciones.
- **Hoyts Abasto** subió bastante: 232 → 470 funciones.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **CEA** lleva 2 días sin ninguna función (traía ~2 por día); entra y sale del cero seguido, puede que no haya programado.
- **Museo del Cine** lleva 1 día sin ninguna función (traía ~1 por día); entra y sale del cero seguido, puede que no haya programado.
- **Centro Cultural de la Cooperación** lleva 2 días sin ninguna función (traía ~3 por día); entra y sale del cero seguido, puede que no haya programado.
- **Sala Lugones**: ticket_url inválido ×6.
- **MALBA**: dos títulos en el mismo horario ×2.
- **Sala Lugones**: dos títulos en el mismo horario ×1.
- 22 funciones sin director: Centro Cultural Borges (13/20), Filo Cine (7/10), Lumiton (2/2).
- 26 funciones sin link de Letterboxd: Amorina (4/6), Centro Cultural Borges (14/20), Hasta Trilce (6/6), Lumiton (2/2).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
