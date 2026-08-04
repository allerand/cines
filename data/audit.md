# Auditoría de la cartelera — martes 4 de agosto

## 🔴 Hay algo para mirar en Lumiton

Datos de hace 15 h · 31 cines · 804 funciones publicadas.

## Para mirar esta semana

- **Lumiton** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Fin de Semana de las Infancias | una Tarde en el Museo | Taller de Juguetes Ópticos'

## Qué cambió desde la semana pasada

- **Cinépolis Recoleta** bajó bastante: 219 → 28 funciones.
- **Hoyts Abasto** bajó bastante: 292 → 109 funciones.
- **Cinemark Palermo** bajó bastante: 228 → 84 funciones.
- **Cinépolis Houssay** bajó bastante: 100 → 13 funciones.
- **Cinemark Caballito** bajó bastante: 136 → 52 funciones.
- **Cine Gaumont** bajó bastante: 81 → 23 funciones.
- **Hoyts Dot** volvió a la cartelera: 0 → 76 funciones.
- **Cinemark Puerto Madero** volvió a la cartelera: 0 → 58 funciones.
- …y 8 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| Cine Gaumont | 23 | 13 | ~66 |

Los otros 30 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Sala Lugones**: ticket_url inválido ×39.
- **Cine York**: dos títulos en el mismo horario ×4.
- 4 funciones sin director: Lumiton (4/6).
- 55 funciones sin link de Letterboxd: Amorina (3/3), Arthaus (13/14), Biblioteca Nacional (2/2), Biblioteca del Congreso (12/12), CCK (12/16), Centro Cultural 25 de Mayo (2/2), Hasta Trilce (6/6), Lumiton (5/6).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
