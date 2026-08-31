# Auditoría de la cartelera — lunes 31 de agosto

## 🔴 Hay 6 cosas para mirar en 6 cines

Datos de hace 4 h · 30 cines · 1871 funciones publicadas.

## Para mirar esta semana

- **MALBA** — la fuente publica 10 ítems en la listing y nosotros tenemos 3 película(s). Puede estar faltando programación.
- **Biblioteca del Congreso** — no tiene ninguna función en la web, pero la fuente publica 2 ítems en la listing. El scraper se rompió.
- **CEA** — se quedó sin funciones (venía de unas 2 por día). Revisá su scraper.
- **Casa del Bicentenario** — se quedó sin funciones (venía de unas 1 por día). Revisá su scraper.
- **CCK** — se quedó sin funciones (venía de unas 7 por día). Revisá su scraper.
- **Arthaus** — se quedó sin funciones (venía de unas 4 por día). Revisá su scraper.

## Qué cambió desde la semana pasada

- **Biblioteca del Congreso** desapareció: 4 → 0 funciones.
- **Arthaus** desapareció: 4 → 0 funciones.
- **Casa del Bicentenario** desapareció: 1 → 0 funciones.
- **Multiplex Belgrano** bajó bastante: 488 → 176 funciones.
- **Cinemark Palermo** bajó bastante: 426 → 134 funciones.
- **Cine Gaumont** bajó bastante: 98 → 40 funciones.
- **MALBA** bajó bastante: 16 → 3 funciones.
- **Cine Cosmos** volvió a la cartelera: 0 → 24 funciones.
- …y 3 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).

## Cines por debajo de lo habitual

| Cine | Funciones | Títulos | Habitual |
|---|---:|---:|---:|
| MALBA | 3 | 3 | ~18 |

Los otros 29 cines están en su rango normal.

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

- **Sala Lugones**: ticket_url inválido ×45.
- **Centro Cultural 25 de Mayo**: director que no es un nombre ×1.
- 12 funciones sin link de Letterboxd: Centro Cultural de la Cooperación (4/4), Hasta Trilce (6/6), Lumiton (2/3).

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`
