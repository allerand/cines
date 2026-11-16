# Auditoría de la cartelera, lunes 16 de noviembre

## 🔴 Hay 27 cosas para mirar

Datos de hace 1 h. Buenos Aires: 41 salas y 4.181 funciones. Madrid: 11 salas y 420 funciones.

## Para mirar esta semana

### Festivales y funcionamiento

- **Buenos Aires Rojo Sangre** (festivales): empieza en 3 días (19 al 29 nov, en Atlas Caballito, Av. Rivadavia 5071) y no está cargado. Fuente: https://www.festivalrojosangre.com.ar/
- **MASS, Semana de los Festivales de Cine de Málaga y San Sebastián** (festivales): empieza en 10 días (26 al 28 nov, en Centro Cultural 25 de Mayo) y no está cargado. Fuente: https://cc25.org/eventos/mass-2026/

### Buenos Aires

- **Centro Cultural Borges** (fuentes): publica 14 funciones pero su fuente no contesta hace 3 días: la API no contesta; se publica el caché de la última corrida buena. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **CCK** (fuentes): publica 9 funciones pero su fuente no contesta hace 3 días: no se pudo leer palaciolibertad.gob.ar/cine/. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **CEA** (fuentes): lleva 30 días sin ninguna función (traía ~2 por día). Revisá su scraper.
- **Centro Cultural de la Cooperación** (fuentes): lleva 3 días sin ninguna función (traía ~2 por día). Revisá su scraper.
- **Centro Cultural Borges** (categorías): el título trae el ciclo pegado adelante (5 casos, 6 funciones). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 18/11 19:00: «Ciclo Cuadro a Cuadro: Ánima Buenos Aires»; 22/11 19:00: «Ingmar Bergman: seis ensayos. PERSONA»; 29/11 19:00: «Ingmar Bergman: seis ensayos. CUANDO HUYE EL DÍA»
- **Centro Cultural 25 de Mayo** (categorías): hay títulos que parecen el nombre de un ciclo o de un festival, sin director ni ficha (1 caso). Confirmar contra la fuente si es una película; si es un ciclo, cargar sus películas una por una. Por ejemplo: 26/11 20:00: «Semana de los Festivales de Cine de Málaga y San Sebastián en Buenos Aires – Mass 2026»
- **Centro Cultural 25 de Mayo** (categorías): el título trae al director pegado (2 casos). El scraper tiene que partirlo: sin eso no encuentra la ficha. Por ejemplo: 01/12 18:00: «El príncipe de Nanawa de Clarisa Navas»; 03/12 19:00: «Encuentro con un Buda (Meeting the Buddha) de Marta György-Kessler»
- **MALBA** (categorías): el título trae al director pegado (1 caso). El scraper tiene que partirlo: sin eso no encuentra la ficha. Por ejemplo: 28/11 24:00: «¿Qué clase de joven le abre la puerta a un vampiro?, de Boom Boom Kid y Zurita»
- **Amorina** (categorías): hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por ejemplo: 20/11 20:00: «Torneo de ajedrez»
- **Filo Cine** (categorías): la columna Ciclo trae el género de la película (2 casos, 10 funciones). El género no es un ciclo: va vacío o con el ciclo de verdad. Por ejemplo: «Documental» («Bajo sospecha: Zokunentu»); «Ficción» («Pizza, birra, faso»)
- **Amorina** (categorías): la columna Ciclo trae el tipo de actividad («Cine») (1 caso, 10 funciones). No es un ciclo: va vacío. Por ejemplo: «Cine» («Twin Peaks»)
- **Sala Lúcida** (categorías): hay ciclos con palabras en mayúsculas (1 caso). Ningún ciclo va gritado: pasarlo por run._fix_caps. Por ejemplo: «CINE en 16mm»
- **Filo Cine** (fichas): hay funciones cuyo título son varias películas juntas (o una película más una charla): así no matchean contra la fuente ni contra Letterboxd y quedan sin director, año ni link. Hay que desagregarlas en una fila por película. Ejemplo: 'La pasarela + El invisible sustento de la frontera'

### Madrid

- **Cines Ideal** (fuentes): publica 30 funciones pero su fuente no contesta hace 25 días: yelmocines.es no devolvió la cartelera (¿Cloudflare?). Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Cines Princesa** (fuentes): lleva 4 días sin ninguna función (traía ~164 por día). Revisá su scraper.
- **Renoir Plaza de España** (fuentes): lleva 4 días sin ninguna función (traía ~86 por día). Revisá su scraper.
- **Renoir Retiro** (fuentes): lleva 4 días sin ninguna función (traía ~58 por día). Revisá su scraper.
- **Cine Estudio** (categorías): el título trae el ciclo pegado adelante (1 caso). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 23/11 18:30: «16º Festival Márgenes: Biografía de Jorge Luis Borges»
- **Embajadores Ercilla** (categorías): el título trae el ciclo pegado adelante (3 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 24/11 20:15: «Universo Villenueve: Incendies»; 01/12 20:15: «Universo Villenueve: La llegada»; 08/12 20:15: «Universo Villenueve: Prisioneros»
- **Embajadores Glorieta** (categorías): el título trae el ciclo pegado adelante (9 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 23/11 17:45: «Ciclo de Cine Peruano: Vino la noche»; 23/11 19:30: «Palestina en pantalla: Con Hasan en Gaza»; 24/11 17:45: «Ciclo de Cine Peruano: Reinas»
- **Golem Madrid** (categorías): el título trae el ciclo pegado adelante (7 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 17/11 22:00: «QueerCineMad: Test»; 19/11 19:00: «XXVII Ciclo de cine foro: Ellas en la ciudad»; 19/11 22:00: «QueerCineMad: Taiga»
- **Sala Equis** (categorías): el título trae el ciclo pegado adelante (9 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 17/11 19:00: «Festival Rizoma-de Brisa y de Sol»; 17/11 21:00: «Festival Rizoma-muchedumbre»; 18/11 17:30: «Festival Rizoma-cherri»
- **Sala Equis** (categorías): hay títulos que parecen el nombre de un ciclo o de un festival, sin director ni ficha (4 casos). Confirmar contra la fuente si es una película; si es un ciclo, cargar sus películas una por una. Por ejemplo: 19/11 22:00: «Festival Rizomalos Días Libres»; 20/11 22:00: «Festival Rizomaperò Abans D’això Hi Haurà Set»; 21/11 19:30: «Ffestival Rizoma-las Mantis»
- **Cines Ideal** (categorías): hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por ejemplo: 01/12 20:15: «El Cascanueces- Ballet Live Roh 26-27»
- **Cineteca Madrid** (categorías): hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por ejemplo: 21/11 20:30: «Entrega de premios + Live A/V: JayDee y Josephine’ Soundscapes»

## Qué cambió desde la semana pasada

- **Centro Cultural de la Cooperación** desapareció: 2 → 0 funciones.
- **Cines Pixel** volvió a la cartelera: 0 → 52 funciones.
- **Universidad del Cine** volvió a la cartelera: 0 → 26 funciones.
- **La Tomada** volvió a la cartelera: 0 → 17 funciones.
- **Casa del Bicentenario** volvió a la cartelera: 0 → 9 funciones.
- **Avalon** volvió a la cartelera: 0 → 5 funciones.
- **Cineclub Farus** volvió a la cartelera: 0 → 5 funciones.
- **Bellas Artes** volvió a la cartelera: 0 → 3 funciones.
- …y 3 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).
- **Cines Princesa** (Madrid) desapareció: 146 → 0 funciones.
- **Renoir Plaza de España** (Madrid) desapareció: 76 → 0 funciones.
- **Renoir Retiro** (Madrid) desapareció: 52 → 0 funciones.

## Festivales

- **FIDBA** (17 al 22 nov, empieza mañana): 34 funciones por delante en 5 salas.
- **Infinito Super 8** (22 al 29 nov, empieza en 6 días): 53 funciones por delante en 4 salas. Tiene 1 cosa para mirar.
- En el radar y sin cargar: **Buenos Aires Rojo Sangre** (19 al 29 nov, empieza en 3 días), **MASS, Semana de los Festivales de Cine de Málaga y San Sebastián** (26 al 28 nov, empieza en 10 días).
- Terminaron hace poco: Fuera de Campo (el 10/11), Festival Internacional de Cine de Mar del Plata (el 15/11).

## Parte de los agentes

Cada uno tiene una sola cosa a cargo y entrega su parte aunque no tenga nada que decir.

| Agente | Qué cuida | Qué revisó | Resultado |
|---|---|---|---|
| Frescura | que el scrape corra todos los días y las stories salgan | 2 carteleras; las stories de 7 días; 58 corridas de 5 workflows en la semana | ✅ sin novedades |
| Fuentes | que ninguna sala se caiga, se quede corta o viva de caché | 50 salas de Buenos Aires con 13 sondas y 120 días de historial; 14 salas de Madrid y 56 días de historial | 🔴 8 para mirar y 🟡 3 pendientes |
| Categorías | que cada dato esté en su casillero: película, ciclo, director, sala | 4.181 funciones de Buenos Aires contra 25 reglas; 420 funciones de Madrid contra 25 reglas; el padrón de index.html (51 salas) | 🔴 16 para mirar y 🟡 11 pendientes |
| Festivales | que ninguno se pase y que los cargados sigan al día | 10 festivales del registro (2 vigentes), 24 del radar y 2 webs | 🔴 2 para mirar y 🟡 1 pendiente |
| Fichas | que cada función tenga sus datos y estén bien escritos | 4.181 funciones de Buenos Aires; 420 funciones de Madrid | 🔴 1 para mirar y 🟡 7 pendientes |

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

### Festivales y funcionamiento

- **Infinito Super 8**: 8 programas sin lista de películas («Rescates: sesión 1», «Competencia Internacional», «Panorama Internacional», «Muestra invitada Curta 8»…): mirar si el festival ya la publicó para cargarlas una por una

### Buenos Aires

- **Cine Cosmos** publica 24 funciones, pero su scraper avisa: cosmos.uba.ar no contesta (HTTP Error 503: Service Temporarily Unavailable); la cartelera sale de Instagram (@cinecosmos.uba).
- **Casa del Bicentenario** publica 9 funciones, pero su scraper avisa: el listado no contesta (HTTP Error 403: Forbidden); sólo queda lo que haya en data/cb_manual.json.
- **Casa del Bicentenario**: su fuente contestó 2 de los últimos 7 días. Hoy anda, pero viene fallando seguido.
- Títulos con la versión o el tipo de sesión pegados (VOSE, 35 mm) (1 caso) en Cine York. Limpiar en el scraper. Por ejemplo: 25/11 20:30: «Vladimir en Buenos Aires en 35 Mm»
- Títulos con un tramo en mayúsculas (7 casos, 8 funciones) en Arthaus, Bellas Artes (2), Centro Cultural Borges (3), Sala Lúcida. Pasarlos por run._fix_caps. Por ejemplo: 19/11 18:00: «RECEN POR MÍ: La historia de Francisco»; 21/11 18:00: «Smyrna (ΣΜΥΡΝΗ ΜΟΥ ΑΓΑΠΗΜΕΝΗ)»
- Funciones cuyo ciclo es el mismo título (1 caso) en Amorina. El ciclo va vacío. Por ejemplo: 20/11 20:00: «Torneo de ajedrez»
- Un mismo ciclo escrito de dos maneras (1 caso) en Sala Lúcida. La búsqueda por ciclo los separa: unificar la escritura. Por ejemplo: «Ruido y Furia . 50 Años de Punk» y «Ruido y Furia. 50 Años de Punk»
- Ciclos con la puntuación rota (2 casos, 4 funciones) en CCK, Sala Lúcida. Arreglar la escritura en el scraper. Por ejemplo: «Ruido y Furia . 50 Años de Punk»; «Miradas contemporáneas:Luis Ortega / Federico Luis»
- Directores de relleno («Desconocido», «Varios») (1 caso, 8 funciones) en Hasta Trilce. Mejor vacío. Por ejemplo: «Película sorpresa»: «Desconocido»
- Directores con años o duraciones adentro (2 casos) en Sala Lúcida (2). El scraper leyó la ficha entera. Por ejemplo: «Ricky Espinosa: El Documental»: «Juan Pablo Duarte. Argentina. 2015. 83 min»; «Nuestra Juventud»: «Roland Steiner. RDA. 1989. 88 min»
- Dos títulos en el mismo horario: Centro Cultural Borges ×3, Cacodelphia ×1. Ejemplo (Centro Cultural Borges): 2026-11-18 19:00: 'Piazzolla, los años del tiburón' vs 'Ciclo Cuadro a Cuadro: Ánima Buenos Aires'
- Sin link de entradas: Sala Lugones ×25. Ejemplo (Sala Lugones): Je’vida
- 4 funciones sin director: Centro Cultural 25 de Mayo (3/4), Museo del Cine (1/1).
- 40 funciones sin link de Letterboxd: Arthaus (7/9), Casa del Bicentenario (7/9), Centro Cultural 25 de Mayo (3/4), Hasta Trilce (8/8), LABA (1/1), La Tomada (13/17), Museo del Cine (1/1).
- 10 títulos sin ningún dato (ni director, ni año, ni duración, ni Letterboxd): puede que no sean películas. Centro Cultural Borges: «Ingmar Bergman: seis ensayos. PERSONA», «ALIENTO - 10 años del Programa de Cine UTDT» y 3 más; MALBA: «Perfume», «¡Película sorpresa!»; Amorina: «Torneo de ajedrez»; Filo Cine: «Proyección de cortometrajes del colectivo Antes Muerto Cine»; Lumiton: «Lo Queer en el Cine de Oro Argentino».

### Madrid

- Títulos con la versión o el tipo de sesión pegados (VOSE, 35 mm) (2 casos) en Artistic Metropol (2). Limpiar en el scraper. Por ejemplo: 18/11 12:00: «CINCO SEGUNDOS V.O.S.E. Sesión Teta»; 19/11 12:00: «EL SER QUERIDO Sesión Teta»
- Títulos con un tramo en mayúsculas (3 casos, 6 funciones) en Artistic Metropol (3). Pasarlos por run._fix_caps. Por ejemplo: 17/11 20:00: «ESTUDIOS DE CINE Noviembre 2026 con Alejandro Mucientes»; 18/11 12:00: «CINCO SEGUNDOS V.O.S.E. Sesión Teta»
- Directores de relleno («Desconocido», «Varios») (2 casos) en Cineteca Madrid (2). Mejor vacío. Por ejemplo: «CIMA Proyecta: 25-N Cortos contra las violencias»: «Varias autoras»; «Colores primarios»: «Varios autores»
- Directores que empiezan con «de» (1 caso) en Embajadores Glorieta. Limpiar en el scraper. Por ejemplo: «Ciclo de Cine Peruano: Reinas»: «de Klaudia Reynicke, Diego Vega»
- Dos títulos en el mismo horario: Golem Madrid ×20, Artistic Metropol ×10, Embajadores Ercilla ×9, Embajadores Glorieta ×5, Cineteca Madrid ×2. Ejemplo (Golem Madrid): 2026-11-16 16:10: 'El tren fluvial' vs 'La voz quebrada'
- 18 títulos sin ningún dato (ni director, ni año, ni duración, ni Letterboxd): puede que no sean películas. Sala Equis: «Festival Rizoma-de Brisa y de Sol», «Festival Rizoma-muchedumbre» y 10 más; Artistic Metropol: «ESTUDIOS DE CINE Noviembre 2026 con Alejandro Mucientes», «Cineclub Garabato»; Cine Estudio: «Película sorpresa»; Cine Doré: «Cortos latinos: Raíces, aromas y color»; Cineteca Madrid: «Capítulo XXXVI: Carta blanca a María Castro y Álvaro Cáceres»; Embajadores Ercilla: «El Apartamento».

## Tablero de fuentes

Cómo viene cada sala: funciones publicadas, hasta qué día llega su programación, cuántas tenía hace una semana, cuántos de los últimos días contestó su fuente, y una barrita por día de las últimas cuatro semanas.

### Buenos Aires

| Sala | Func. | Títulos | Hasta | Hace 7 días | Fuente | Cuatro semanas |
|---|---:|---:|---|---:|---|---|
| 🟢 Sala Lugones | 65 | 33 | 13/12 | 51 | 7 de 7 días | `▆▅▅▅▅▄▄▄▄▄▃▃████▇▇▇▆▆▆▇▇▇▆▆█` |
| 🟢 Cine Gaumont | 37 | 14 | 18/11 | 36 | 7 de 7 días | `█▇▇▆▅▄▃▇▇▆▅▅▄▃▇▆▅▅▄▄▃▂▆▆▅▅▄▃` |
| 🟢 Cine Lorca | 33 | 6 | 18/11 | 30 | 7 de 7 días | `▃▂▇▆▆▅▄▃▂▇▆▆▅▄▃▂▇▆▆▅▄▃▂█▇▆▅▄` |
| 🟢 Cacodelphia | 31 | 15 | 29/11 | 41 | 7 de 7 días | `▃▇▆▅▅▄▄▃▇▆▆▅▄▃▂██▇▇▆▅▄▇▇▆▆▅▄` |
| 🟢 Cine York | 31 | 31 | 29/11 | 37 | 7 de 7 días | `▅▅▅▅▄▄▄▄███▇▇▇▇▇██▇▇▇▇▇▇▇▆▆▆` |
| 🟢 MALBA | 28 | 20 | 5/12 | 39 | 7 de 7 días | `▇▆▆▅▄▃▃▃▄▄▇▇▆▆▇███▇▇▆▆▆▆▆▅▅▅` |
| 🟢 Universidad del Cine | 26 | 26 | 27/11 | 0 | a mano | `__________________________██` |
| 🟡 Cine Cosmos | 24 | 7 | 18/11 | 8 | 7 de 7 días | `▃▂___▅▄▃▂█▇▆▅▄▃▂▆▅▄▃▂▂▂█▇▆▅▄` |
| 🟢 Sala Lúcida | 23 | 22 | 22/11 | 12 | 7 de 7 días | `▄▄▄▄▃▄▄▄▄▄▄▄▄▄▄▄▄▄▄▅▅▅▅▅▅▅██` |
| 🟢 Amorina | 17 | 13 | 19/12 | 22 | 7 de 7 días | `▃▃▇██▇▇▇▇▇▇▇▇▆██▇▇▇▇▇▆▆▆▆▆▆▅` |
| 🟢 La Tomada | 17 | 17 | 28/11 | 0 | a mano | `__________________________██` |
| 🔴 Centro Cultural Borges | 14 | 10 | 13/12 | 25 | caída hace 3 días | `▃▃▃▃▃▃▃▃▃█▇▆▃▃▃▃▃▃▃▃▃▃▃▃▂▂▂▂` |
| 🟢 Centro Cultural Recoleta | 11 | 11 | 29/11 | 6 | 7 de 7 días | `▇▇▇▆▅▅▃▃▅▆▇▇▆▅▅▅▅▅▆▆▅▅▅▅▅▄█▇` |
| 🟢 Filo Cine | 10 | 10 | 27/11 | 9 | 7 de 7 días | `█▇▇▇▅▅▅▅▄▇▇▇▇▇▇▇▇▇▇▇▇██▇▇███` |
| 🟢 Arthaus | 9 | 9 | 29/11 | 4 | 7 de 7 días | `▄▄▄▄▃▂▂▂▂▂▂▂▂▂▂▂▄▄▄▄▄▄▄▄▄▃█▇` |
| 🔴 CCK | 9 | 7 | 29/11 | 16 | caída hace 3 días | `▅▅▅▅▄▃▂▂▅███▇▆▆▆▆▆▆▆▆▆▆▆▆▆▄▄` |
| 🟡 Casa del Bicentenario | 9 | 9 | 29/11 | 0 | a mano | `_____█▇▇▇▇▇▆▅▁▁▁▁▁▁_______▅▅` |
| 🟢 Centro Cultural Munro | 9 | 9 | 6/12 | 12 | 7 de 7 días | `▃▃▃▃▃▃▂▂▇▇▇▇▇▆▆▆████▇▇▆▆▆▆▆▅` |
| 🟢 Hasta Trilce | 8 | 1 | 8/12 | 6 | 7 de 7 días | `▆▅▅▆▆▆▆▆▆▆▆▆▆▆▆▅▆▆▆▆▆█▆▆▆▆▆█` |
| 🟢 Avalon | 5 | 5 | 21/11 | 0 | a mano | `__________________________██` |
| 🟢 Cineclub Farus | 5 | 5 | 27/11 | 0 | 2 de 2 días | `▇▇▄▄▄▄▄▄▄_________________██` |
| 🟢 Biblioteca del Congreso | 4 | 4 | 26/11 | 5 | 7 de 7 días | `▆▅▅▃▃_▃▃▂▂_██████▇▇▇▇▇▇▇▆▆▆▆` |
| 🟢 Centro Cultural 25 de Mayo | 4 | 4 | 3/12 | 5 | 7 de 7 días | `▄▄▄▂_▂▂▂▂▇▇█████████████▇▇_▇` |
| 🟢 Bellas Artes | 3 | 3 | 28/11 | 0 | 5 de 5 días | `████▇▆▆▆▆▆▆▅▃▃▃▃▃▃▃____▅▅▄▃▃` |
| 🟢 Lumiton | 2 | 2 | 25/11 | 3 | 7 de 7 días | `▅▅▅▃▃▃▃████▆▆▆▆▆▅▅▆▆▆▆▆▆▆▆▅▅` |
| 🟢 Biblioteca Nacional | 1 | 1 | 24/11 | 1 | 7 de 7 días | `____███████████▅▅▅▅▅▅▅▅▅▅▅▅▅` |
| 🟢 LABA | 1 | 1 | 17/11 | 0 | a mano | `__________________________██` |
| 🟢 Museo del Cine | 1 | 1 | 29/11 | 0 | a mano | `__________________________██` |
| 🔴 CEA | 0 | 0 |  | 0 |  | `____________________________` |
| 🔴 Centro Cultural de la Cooperación | 0 | 0 |  | 2 | 5 de 5 días | `▅▅▃▃█████_▆▆▆▆▆▆▅▅▅▅▅▅▅▃▃___` |
| 🟢 Hoyts Abasto | 556 | 23 | 29/12 | 540 | 7 de 7 días | `▅▇▇▇▆▆▆▅█▇▇▆▆▆▅▇█▇▇▆▆▅██▇▇▆▆` |
| 🟢 Cinemark Palermo | 496 | 18 | 23/12 | 470 | 7 de 7 días | `▅▇▇▇▆▆▅▅█▇▇▆▆▅▅▇█▇▇▆▆▆███▇▇▆` |
| 🟢 Hoyts Dot | 432 | 18 | 29/12 | 409 | 7 de 7 días | `▅▇█▇▇▆▆▅█▇▇▇▆▅▅▇▇▇▆▆▆▅▅█▇▇▆▆` |
| 🟢 Multiplex Pilar | 425 | 18 | 23/12 | 408 | 7 de 7 días | `▇▇▇▇▆▆▅▇▇▆▆▅▅▄▄▇▆▇▆▆▅██▇▇▆▆▅` |
| 🟢 Cinemark Puerto Madero | 383 | 18 | 29/12 | 366 | 7 de 7 días | `▇▇▇▇▆▆▅▅██▇▇▆▆███▇▇▆▆▆███▇▇▆` |
| 🟢 Multiplex Belgrano | 366 | 19 | 23/12 | 341 | 7 de 7 días | `▇▇▆▆▆▅▄█▇▇▆▆▅▄█▇▇▇▆▆▅▄██▇▆▆▅` |
| 🟢 Multiplex Lavalle | 351 | 18 | 23/12 | 309 | 7 de 7 días | `▇▇█▇▇▆▇█▇▇▆▆▆▅▇▇▆▇▆▆▅███▇▇▆▆` |
| 🟢 Multiplex Canning | 322 | 15 | 23/12 | 314 | 7 de 7 días | `▇▇█▇▇▆▆▆█▇▇▇▆▆█▇▇▇▇▆▆███▇▇▆▆` |
| 🟢 Cinemark Caballito | 254 | 14 | 29/12 | 256 | 7 de 7 días | `▅▇█▇▇▆▆▅█▇▇▆▆▅▅▇█▇▇▆▆▅██▇▇▆▆` |
| 🟢 Cines Pixel | 52 | 13 | 22/11 | 0 | 1 de 1 días | `___________________________█` |
| 🟢 Cinépolis Recoleta | 49 | 16 | 16/11 | 31 | 7 de 7 días | `▇█▇██▇█▇▇▇▇▇▇█▇▇▆▅▅▅▅▅▅▆██▇█` |
| 🟢 Showcase Belgrano | 40 | 15 | 16/11 | 39 | 7 de 7 días | `████▇▇▇▇▇▇███████▇▇▇▇▇▇▇█▇▇▇` |
| 🟢 Cinépolis Houssay | 18 | 8 | 16/11 | 17 | 7 de 7 días | `███▆▄▂_▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃` |

Sin funciones y sin nada que marcar (salas de festival o que programan cada tanto): Centro Cultural Leopoldo Marechal (desde el 8/11), Club Lucero (desde el 30/10), Escuela Da Vinci (desde el 31/10), FADU (desde el 7/10), Museo Moderno (desde el 25/10), Sala Mario Soffici (desde el 21/8).

### Madrid

| Sala | Func. | Títulos | Hasta | Hace 7 días | Fuente | Cuatro semanas |
|---|---:|---:|---|---:|---|---|
| 🟢 Golem Madrid | 70 | 17 | 22/11 | 64 | 7 de 7 días | `▄██▇▆▅▄▄▇▇▇▆▆▅▄███▇▆▅▃▇▇█▇▆▅` |
| 🟢 Embajadores Glorieta | 64 | 36 | 27/12 | 56 | 7 de 7 días | `▄█▇▇▆▅▅▄█▇▇▆▅▄▄▇▇▆▆▅▄▄▇▇▇▇▆▅` |
| 🟢 Embajadores Ercilla | 58 | 33 | 15/12 | 57 | 7 de 7 días | `▅█▇▇▆▅▄▄█▇▇▆▅▄▄██▇▇▆▅▄█▇▇▆▆▅` |
| 🟢 Cineteca Madrid | 47 | 41 | 3/1 | 47 | 7 de 7 días | `▆▆▆▆▅▅▅▅▇▆███▇▇▇▇▆▆▆▅▆▆▆▇▆▆▅` |
| 🟢 Cine Doré | 46 | 45 | 16/12 | 63 | 7 de 7 días | `▄▄▄▃▂▃▃▃▂▂▇▇██▂▂▂▂▂████▇▇▆▆▆` |
| 🟢 Sala Equis | 31 | 27 | 29/11 | 45 | 7 de 7 días | `___________██▇▇▇▇▇▆▆▆▆▆▆▅▅▅▄` |
| 🟢 Artistic Metropol | 30 | 18 | 26/11 | 41 | 7 de 7 días | `▄▇▆▅▅▅▄▅▅▆▅▅▅▅▅▅▇▇▆▅▆▅█▇▆▅▅▅` |
| 🔴 Cines Ideal | 30 | 3 | 20/12 | 30 | caída hace 25 días | `█▇▅▄▄▃▃▃▃▃▃▃▃▃▃▃▃▃▃▂▂▂▂▂▂▂▂▂` |
| 🟢 Cine Estudio | 17 | 17 | 25/11 | 30 | 7 de 7 días | `▄▄▆▅▅▅▄▄▅▆▆▅▅▄▄▄██▇▇▆▆▆▆▅▅▄▄` |
| 🟢 Museo Reina Sofía | 14 | 14 | 12/12 | 12 | 7 de 7 días | `_____█▅▅▅▅▅▅▅▅▅▅▅▅▄▄▄▄▄▄▃▂▂▄` |
| 🟢 Cines Callao | 13 | 3 | 19/11 | 14 | 7 de 7 días | `▄▃█▇▆▅▄▃▇▆▆▅▅▃▂▇▆▆▅▄▃▂▇▆▆▅▄▃` |
| 🔴 Cines Princesa | 0 | 0 |  | 146 | 0 de 3 días | `▄███▇▆▅▄███▇▆▅▄███▇▆▅▄▃▂____` |
| 🔴 Renoir Plaza de España | 0 | 0 |  | 76 | 0 de 3 días | `▄███▇▆▅▄███▇▆▅▄███▇▆▅▄▃▂____` |
| 🔴 Renoir Retiro | 0 | 0 |  | 52 | 0 de 3 días | `▄███▇▆▅▄███▇▆▅▄▇▇█▇▆▅▄▃▂____` |

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`. Para que los agentes revisen y arreglen lo que encontró: `/auditoria` en Claude.
