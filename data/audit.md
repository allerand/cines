# Auditoría de la cartelera — lunes 10 de agosto

## 🔴 Hay 5 cosas para mirar en 5 cines

Datos de hace 5 h · 31 cines · 1998 funciones publicadas.

## Para mirar esta semana

- **CEA** — se quedó sin funciones (venía de unas 2 por día). Revisá su scraper.
- **Centro Cultural de la Cooperación** — se quedó sin funciones (venía de unas 1 por día). Revisá su scraper.
- **Amorina** — se quedó sin funciones (venía de unas 3 por día). Revisá su scraper.
- **Cine Cosmos** — se quedó sin funciones (venía de unas 8 por día). Revisá su scraper.
- **Lumiton** — el título en realidad es el copete del ciclo o una actividad, no una película. Ejemplo: 'Fin de Semana de la Infancia | una Tarde en el Museo | la Magia de la Luz: Taller de Cianotipia'

## Qué cambió desde la semana pasada

- **Cine Cosmos** desapareció: 24 → 0 funciones.
- **Centro Cultural de la Cooperación** desapareció: 1 → 0 funciones.
- **Cine Lorca** bajó bastante: 33 → 9 funciones.
- **Multiplex Lavalle** volvió a la cartelera: 0 → 344 funciones.
- **Hoyts Dot** volvió a la cartelera: 0 → 203 funciones.
- **Multiplex Belgrano** volvió a la cartelera: 0 → 159 funciones.
- **Multiplex Pilar** volvió a la cartelera: 0 → 144 funciones.
- **Cinemark Puerto Madero** volvió a la cartelera: 0 → 133 funciones.
- …y 9 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Sala Lugones**: ticket_url inválido ×58.
- **Cine York**: dos títulos en el mismo horario ×4.
- **Cine Lorca**: dos títulos en el mismo horario ×1.
- 3 funciones sin director: Lumiton (3/4).
- 12 funciones sin link de Letterboxd: Centro Cultural Recoleta (2/3), Hasta Trilce (6/6), Lumiton (4/4).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
