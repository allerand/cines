# Auditoría de la cartelera — lunes 12 de octubre

## 🔴 Hay 4 cosas para mirar en 4 cines

Datos de hace 10 h · 35 cines · 2036 funciones publicadas.

## Para mirar esta semana

- **Casa del Bicentenario** — lleva 14 días sin ninguna función, y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.
- **FADU** — lleva 5 días sin ninguna función (traía ~5 por día). Revisá su scraper.
- **Biblioteca Nacional** — lleva 14 días sin ninguna función, pero la fuente publica 1 ítems en la listing. El scraper se rompió.
- **Sala Lugones** — hay horarios que no se pudieron parsear (×2). Ejemplo: Cinema Kabuki: '??'

## Qué cambió desde la semana pasada

- **FADU** desapareció: 5 → 0 funciones.
- **Cacodelphia** bajó bastante: 77 → 30 funciones.
- **Cine Gaumont** volvió a la cartelera: 0 → 38 funciones.
- **Museo del Cine** volvió a la cartelera: 0 → 2 funciones.
- **Cinépolis Houssay** subió bastante: 19 → 64 funciones.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **CEA** lleva 1 día sin ninguna función (traía ~4 por día); entra y sale del cero seguido, puede que no haya programado.
- **Sala Lugones**: ticket_url inválido ×23.
- **MALBA**: dos títulos en el mismo horario ×2.
- **Sala Lugones**: dos títulos en el mismo horario ×1.
- 8 funciones sin director: Filo Cine (7/8), Lumiton (1/1).
- 19 funciones sin link de Letterboxd: Centro Cultural 25 de Mayo (2/3), Centro Cultural de la Cooperación (3/3), Filo Cine (5/8), Hasta Trilce (6/6), Lumiton (1/1), Museo del Cine (2/2).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
