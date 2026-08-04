# Auditoría de la cartelera — martes 4 de agosto

## 🔴 Hay algo para mirar en Lumiton

Datos de hace 3 h · 31 cines · 1041 funciones publicadas.

## Para mirar esta semana

- **Lumiton** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Fin de Semana de las Infancias | una Tarde en el Museo | Taller de Juguetes Ópticos'

## Qué cambió desde la semana pasada

- **Cinépolis Recoleta** bajó bastante: 219 → 30 funciones.
- **Cinépolis Houssay** bajó bastante: 100 → 16 funciones.
- **Hoyts Dot** volvió a la cartelera: 0 → 108 funciones.
- **Cinemark Puerto Madero** volvió a la cartelera: 0 → 88 funciones.
- **Showcase Belgrano** volvió a la cartelera: 0 → 38 funciones.
- **Casa del Bicentenario** volvió a la cartelera: 0 → 10 funciones.
- **Cine Lorca** volvió a la cartelera: 0 → 9 funciones.
- **Hasta Trilce** volvió a la cartelera: 0 → 6 funciones.
- …y 4 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Cine Cosmos | 8 | 6 | ~32 |

Los otros 30 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Sala Lugones**: ticket_url inválido ×39.
- **Cine York**: dos títulos en el mismo horario ×4.
- 4 funciones sin director: Lumiton (4/6).
- 12 funciones sin link de Letterboxd: Hasta Trilce (6/6), Lumiton (6/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
