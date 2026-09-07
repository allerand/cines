# Auditoría de la cartelera — lunes 7 de septiembre

## 🔴 Hay algo para mirar en Casa del Bicentenario

Datos de hace 5 h · 34 cines · 1794 funciones publicadas.

## Para mirar esta semana

- **Casa del Bicentenario** — lleva 8 días sin ninguna función (traía ~1 por día), y la fuente tampoco nos deja sondearla (HTTP 403). No es el parser: es acceso al sitio — revisá que el proxy de scraping siga vivo.

## Qué cambió desde la semana pasada

- **Multiplex Lavalle** bajó bastante: 372 → 162 funciones.
- **Cinépolis Recoleta** bajó bastante: 48 → 22 funciones.
- **Sala Lúcida** volvió a la cartelera: 0 → 11 funciones.
- **CCK** volvió a la cartelera: 0 → 10 funciones.
- **Arthaus** volvió a la cartelera: 0 → 8 funciones.
- **Biblioteca del Congreso** volvió a la cartelera: 0 → 7 funciones.
- **Centro Cultural Borges** subió bastante: 8 → 21 funciones.

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Cine Lorca | 2 | 2 | ~8 |

Los otros 33 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **CEA** lleva 1 día sin ninguna función (traía ~3 por día); entra y sale del cero seguido, puede que no haya programado.
- **Sala Lugones**: ticket_url inválido ×9.
- **Centro Cultural Borges**: director que no es un nombre ×8.
- 9 funciones sin link de Letterboxd: Centro Cultural de la Cooperación (3/3), Hasta Trilce (6/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
