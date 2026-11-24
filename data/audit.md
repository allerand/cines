# Auditoría de la cartelera, martes 24 de noviembre

## 🔴 Hay 18 cosas para mirar, 7 nuevas

Datos de hace 10 h. Buenos Aires: 45 salas y 3.083 funciones. Madrid: 14 salas y 742 funciones.

## Nuevo esta semana

### Festivales y funcionamiento

- **Bazofi** (festivales): su web cambió desde el 20/11: 1 línea nueva y 1 que ya no está. Lo nuevo: «Hoy abierto de 12:00 a 20:00». Revisar la grilla contra lo cargado: https://malba.org.ar/evento/bazofi-2026/

### Buenos Aires

- **Sala Lúcida** (fuentes): la fuente publica 22 ítems en la listing y nosotros tenemos 7 película(s). Puede estar faltando programación.
- **Espacio INCAA Morón** (fuentes): la fuente publica 15 ítems en la listing y nosotros tenemos 5 película(s). Puede estar faltando programación.
- **Cine Gaumont** (categorías): hay títulos que parecen el nombre de un ciclo o de un festival, sin director ni ficha (1 caso, 7 funciones). Confirmar contra la fuente si es una película; si es un ciclo, cargar sus películas una por una. Por ejemplo: 26/11 19:00: «41° Festival Internacional MDQ en Gaumont - BORGES AND ME»

### Madrid

- **Cineteca Madrid** (categorías): el título trae el ciclo pegado adelante (3 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 12/12 11:30: «El personaje animado: Taller para familias»; 12/12 16:00: «El personaje animado: Taller dirigido a adultos»; 13/12 11:00: «El personaje animado: Taller para jóvenes»
- **Artistic Metropol** (categorías): el título trae al director pegado (1 caso, 2 funciones). El scraper tiene que partirlo: sin eso no encuentra la ficha. Por ejemplo: 24/11 16:00: «Noche y día, de Virginia Woolf»
- **Cineteca Madrid** (fichas): el título en realidad es el copete del ciclo o una actividad, no una película (×6). Ejemplo: 'Relatos de los relatos. Historias y genealogías de las músicas experimentales y el arte sonoro en España'

## Sigue abierto

Ya salió en un informe anterior y todavía no se arregló.

### Festivales y funcionamiento

- **MASS** (festivales, desde el 17/11): su web cambió desde el 16/11: 97 líneas nuevas y 1 que ya no está. Lo nuevo: «Lo mejor de los festivales de Málaga y San Sebastián llega al Centro Cultural 25 de Mayo.»; «Del 26 al 28 de noviembre, la muestra MASS 2026 reunirá seis películas del cine español co»; «– YO NO MORIRÉ DE AMOR, de Mɑrtɑ Mɑtute – 26 de noviembre a las 18hs». Revisar la grilla contra lo cargado: https://cc25.org/eventos/mass-2026/

### Buenos Aires

- **CCK** (fuentes, desde el 16/11): publica 5 funciones pero su fuente no contesta hace 10 días: no se pudo leer palaciolibertad.gob.ar/cine/. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Centro Cultural Borges** (fuentes, desde el 16/11): publica 5 funciones pero su fuente no contesta hace 10 días: la API no contesta; se publica el caché de la última corrida buena. Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Centro Cultural de la Cooperación** (fuentes, desde el 16/11): lleva 5 días sin ninguna función (traía ~1 por día). Revisá su scraper.
- **Centro Cultural 25 de Mayo** (categorías, desde el 16/11): el título trae al director pegado (2 casos). El scraper tiene que partirlo: sin eso no encuentra la ficha. Por ejemplo: 01/12 18:00: «El príncipe de Nanawa de Clarisa Navas»; 03/12 19:00: «Encuentro con un Buda (Meeting the Buddha) de Marta György-Kessler»
- **Filo Cine** (categorías, desde el 16/11): la columna Ciclo trae el género de la película (2 casos, 5 funciones). El género no es un ciclo: va vacío o con el ciclo de verdad. Por ejemplo: «Documental» («¡ABRAN LOS ARCHIVOS! Proyección de cortometrajes del colectivo Antes Muerto Cine»); «Ficción» («Movimiento»)
- **Amorina** (categorías, desde el 16/11): la columna Ciclo trae el tipo de actividad («Cine») (1 caso, 6 funciones). No es un ciclo: va vacío. Por ejemplo: «Cine» («Twin Peaks»)

### Madrid

- **Cines Ideal** (fuentes, desde el 16/11): publica 210 funciones pero no scrapeó ninguna en la última corrida: yelmocines.es no devolvió la cartelera (¿Cloudflare?). Lo que se ve es lo último bueno, y se vacía solo a medida que pasan las fechas.
- **Embajadores Ercilla** (categorías, desde el 16/11): el título trae el ciclo pegado adelante (3 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 24/11 20:15: «Universo Villenueve: Incendies»; 01/12 20:15: «Universo Villenueve: La llegada»; 08/12 20:15: «Universo Villenueve: Prisioneros»
- **Embajadores Glorieta** (categorías, desde el 16/11): el título trae el ciclo pegado adelante (7 casos). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 24/11 17:45: «Ciclo de Cine Peruano: Reinas»; 25/11 17:45: «Ciclo de Cine Peruano: Yana Wara»; 26/11 17:45: «Ciclo de Cine Peruano: Manco Cápac»
- **Golem Madrid** (categorías, desde el 16/11): el título trae el ciclo pegado adelante (1 caso). El scraper tiene que partirlo: el ciclo a su columna y el título solo. Por ejemplo: 26/11 19:00: «XXVII Ciclo de cine foro: Soulèvements»

## Qué cambió desde la semana pasada

- **Cinépolis Recoleta** desapareció: 45 → 0 funciones.
- **Showcase Belgrano** desapareció: 40 → 0 funciones.
- **Cine Lorca** desapareció: 22 → 0 funciones.
- **Cinépolis Houssay** desapareció: 18 → 0 funciones.
- **Avalon** desapareció: 5 → 0 funciones.
- **Centro Cultural de la Cooperación** desapareció: 1 → 0 funciones.
- **LABA** desapareció: 1 → 0 funciones.
- **Multiplex Belgrano** bajó bastante: 545 → 240 funciones.
- …y 17 cines más con cambios de tamaño parecido (corré `python3 scripts/audit.py` para verlos).
- **Sala Equis** (Madrid) bajó bastante: 28 → 12 funciones.
- **Cines Princesa** (Madrid) volvió a la cartelera: 0 → 111 funciones.
- **Renoir Plaza de España** (Madrid) volvió a la cartelera: 0 → 57 funciones.
- **Renoir Retiro** (Madrid) volvió a la cartelera: 0 → 36 funciones.
- **Cines Ideal** (Madrid) subió bastante: 30 → 210 funciones.
- Se resolvió: CEA: lleva 30 días sin ninguna función (traía ~2 por día). Revisá su scraper. (estaba desde el 16/11)
- Se resolvió: Cines Princesa: lleva 4 días sin ninguna función (traía ~164 por día). Revisá su scraper. (estaba desde el 16/11)
- Se resolvió: Renoir Plaza de España: lleva 4 días sin ninguna función (traía ~86 por día). Revisá su scraper. (estaba desde el 16/11)
- Se resolvió: Renoir Retiro: lleva 4 días sin ninguna función (traía ~58 por día). Revisá su scraper. (estaba desde el 16/11)
- Se resolvió: Filo Cine: hay funciones cuyo título son varias películas juntas (o una película más una charla): así no matchean… (estaba desde el 16/11)
- Se resolvió: MALBA: el título trae al director pegado (1 caso). El scraper tiene que partirlo: sin eso no encuentra la ficha.… (estaba desde el 16/11)
- Se resolvió: Cine Estudio: el título trae al director pegado (1 caso). El scraper tiene que partirlo: sin eso no encuentra la ficha.… (estaba desde el 19/11)
- Se resolvió: Amorina: hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por… (estaba desde el 16/11)
- Se resolvió: Biblioteca Nacional: lleva 1 día sin ninguna función (traía ~1 por día), pero la fuente publica 2 ítems en la listing. El… (estaba desde el 20/11)
- Se resolvió: Sala Equis: el título trae el ciclo pegado adelante (9 casos). El scraper tiene que partirlo: el ciclo a su columna y… (estaba desde el 16/11)
- Se resolvió: Cines Ideal: hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por… (estaba desde el 16/11)
- Se resolvió: Cineteca Madrid: hay actividades que no son películas (1 caso). Se descartan en el scraper o en manual_screenings.json. Por… (estaba desde el 16/11)
- Se resolvió: Sala Lúcida: hay ciclos con palabras en mayúsculas (1 caso). Ningún ciclo va gritado: pasarlo por run._fix_caps. Por… (estaba desde el 16/11)
- Se resolvió: Cine Estudio: el título trae el ciclo pegado adelante (1 caso). El scraper tiene que partirlo: el ciclo a su columna y… (estaba desde el 16/11)
- Se resolvió: Sala Equis: hay títulos que parecen el nombre de un ciclo o de un festival, sin director ni ficha (3 casos). Confirmar… (estaba desde el 16/11)

## Festivales

- **Bazofi** (5 al 26 nov, en curso, quedan 2 días): 4 funciones por delante en 1 sala. Tiene 2 cosas para mirar.
- **Buenos Aires Rojo Sangre** (19 al 29 nov, en curso, quedan 5 días): 122 funciones por delante en 1 sala. Tiene 1 cosa para mirar.
- **Infinito Super 8** (22 al 29 nov, en curso, quedan 5 días): 37 funciones por delante en 4 salas. Tiene 2 cosas para mirar.
- **Festival de Cine Indígena BAIn** (25 al 29 nov, empieza mañana): 1 función por delante en 1 sala. Tiene 1 cosa para mirar.
- **MASS** (26 al 28 nov, empieza en 2 días): 6 funciones por delante en 1 sala. Tiene 1 cosa para mirar.
- Terminaron hace poco: Fuera de Campo (el 10/11), Festival Internacional de Cine de Mar del Plata (el 15/11), FIDBA (el 22/11).

## Parte de los agentes

Cada uno tiene una sola cosa a cargo y entrega su parte aunque no tenga nada que decir.

| Agente | Qué cuida | Qué revisó | Resultado |
|---|---|---|---|
| Frescura | que el scrape corra todos los días y las stories salgan | 2 carteleras; las stories de 7 días; 83 corridas de 5 workflows en la semana | 🟡 1 pendiente |
| Fuentes | que ninguna sala se caiga, se quede corta o viva de caché | 58 salas de Buenos Aires con 17 sondas y 120 días de historial; 14 salas de Madrid y 63 días de historial | 🔴 6 para mirar y 🟡 5 pendientes |
| Categorías | que cada dato esté en su casillero: película, ciclo, director, sala | 3.083 funciones de Buenos Aires contra 25 reglas; 742 funciones de Madrid contra 25 reglas; el padrón de index.html (59 salas) | 🔴 9 para mirar y 🟡 10 pendientes |
| Festivales | que ninguno se pase y que los cargados sigan al día | 14 festivales del registro (5 vigentes), 24 del radar y 4 webs | 🔴 2 para mirar y 🟡 6 pendientes |
| Fichas | que cada función tenga sus datos y estén bien escritos | 3.083 funciones de Buenos Aires; 742 funciones de Madrid | 🔴 1 para mirar y 🟡 10 pendientes |

## Pendientes de siempre

Cosas que no rompen la web pero degradan la ficha. Están acá para que no se olviden, no para arreglarlas hoy.

### Festivales y funcionamiento

- **Post to Instagram** (workflow): fallaron 3 de 34 corridas de la semana, la última el 23/11.
- **Bazofi**: 1 función fuera de sus fechas (5 al 26 nov): MALBA, 2026-11-27, «Orar Orbil & viceversa». O el registro tiene mal las fechas o la función no es del festival
- **Infinito Super 8**: 7 programas sin lista de películas («Competencia Internacional», «Panorama Internacional», «Muestra invitada Curta 8», «Muestra de talleres: Cine Oculta y Moira Lacowicz»…): mirar si el festival ya la publicó para cargarlas una por una
- **Buenos Aires Rojo Sangre**: 2 programas sin lista de películas («Fin de semana sangriento: bloque 6», «Muestra Federal de Cine de Terror»): mirar si el festival ya la publicó para cargarlas una por una
- **Infinito Super 8**: su web cambió desde el 17/11: 1 línea nueva. Lo nuevo: «DEL MÁS ALLÁ». Revisar la grilla contra lo cargado: https://www.infinitosuper8.com.ar/
- **Festival de Cine Indígena BAIn**: no se pudo leer su web (HTTP 400): esta semana no se sabe si cambió la grilla. https://www.facebook.com/FestivalDeCineBuenosAiresIndigenaBaIn/
- **Festival Internacional de Cine de Arquitectura y Diseño de Buenos Aires** (2 funciones en Sala Lúcida) aparece en la pestaña Festivales con el nombre del ciclo, porque dice «festival» y no está en data/festivales.json. Si es un festival, registrarlo con nombre, fechas y logo.

### Buenos Aires

- **Casa del Bicentenario** publica 7 funciones, pero su scraper avisa: el listado no contesta (HTTP Error 403: Forbidden); sólo queda lo que haya en data/cb_manual.json.
- **Centro Cultural Borges** está por debajo de lo habitual: 5 funciones de 5 películas, contra ~14 de siempre.
- **La Tomada** está por debajo de lo habitual: 3 funciones de 3 películas, contra ~17 de siempre.
- **Arthaus** está por debajo de lo habitual: 2 funciones de 2 películas, contra ~6 de siempre.
- Se quedan sin programación entre hoy y mañana: Lumiton (hasta el 25/11; suele tener ~16 días por delante). Si su web ya publicó lo que sigue, el scraper no lo está viendo.
- Títulos con la versión o el tipo de sesión pegados (VOSE, 35 mm) (1 caso) en Cine York. Limpiar en el scraper. Por ejemplo: 25/11 20:30: «Vladimir en Buenos Aires en 35 Mm»
- Títulos con un tramo en mayúsculas (3 casos, 9 funciones) en Bellas Artes, Cine Gaumont, Filo Cine. Pasarlos por run._fix_caps. Por ejemplo: 24/11 18:00: «¡ABRAN LOS ARCHIVOS! Proyección de cortometrajes del colectivo Antes Muerto Cine»; 26/11 19:00: «41° Festival Internacional MDQ en Gaumont - BORGES AND ME»
- Ciclos con la puntuación rota (1 caso, 2 funciones) en CCK. Arreglar la escritura en el scraper. Por ejemplo: «Miradas contemporáneas:Luis Ortega / Federico Luis»
- Directores de relleno («Desconocido», «Varios») (2 casos, 7 funciones) en Atlas Caballito, Hasta Trilce. Mejor vacío. Por ejemplo: «Película sorpresa»: «Desconocido»; «Yumemonogatari: The living Dragon»: «Varios directores»
- Directores con años o duraciones adentro (2 casos) en Sala Lúcida (2). El scraper leyó la ficha entera. Por ejemplo: «Artacho Jurado, Sinfonia de un Arquitecto»: «Teresa Eça y Pedro Gorski - Brasil - 82 min - 2026»; «La Ricarda, Melodia de una Casa»: «Morrosko Vila-San-Juan - España - 70 min - 2026»
- Director que no es un nombre: Sala Lúcida ×2. Ejemplo (Sala Lúcida): Artacho Jurado, Sinfonia de un Arquitecto: 'Teresa Eça y Pedro Gorski - Brasil - 82 min - 2026'
- Dos títulos en el mismo horario: Atlas Caballito ×23, Cacodelphia ×1, Espacio INCAA Morón ×1, MALBA ×1. Ejemplo (Atlas Caballito): 2026-11-24 16:00: 'Juego maldito' vs 'Jingle Hell'
- Sin link de entradas: Sala Lugones ×19. Ejemplo (Sala Lugones): El pecado de Cluny Brown
- 6 funciones sin director: CEA (1/1), La Tomada (3/3), Lumiton (1/1), Museo del Cine (1/1).
- 18 funciones sin link de Letterboxd: CEA (1/1), Casa del Bicentenario (6/7), Hasta Trilce (6/6), La Tomada (3/3), Lumiton (1/1), Museo del Cine (1/1).
- 3 títulos sin ningún dato (ni director, ni año, ni duración, ni Letterboxd): puede que no sean películas. Filo Cine: «¡ABRAN LOS ARCHIVOS! Proyección de cortometrajes del colectivo Antes Muerto Cine»; Lumiton: «Lo Queer en el Cine de Oro Argentino»; Centro Cultural Borges: «ALIENTO - 10 años del Programa de Cine UTDT».

### Madrid

- Títulos con la versión o el tipo de sesión pegados (VOSE, 35 mm) (1 caso) en Artistic Metropol. Limpiar en el scraper. Por ejemplo: 26/11 12:00: «VIRGINIA WOOLF: NOCHE Y DÍA V.O.S.E. Sesión Teta»
- Títulos con el año o la duración pegados (1 caso) en Cines Ideal. Limpiar en el scraper. Por ejemplo: 24/11 21:30: «Dune (1984) - Reestreno»
- Títulos con un tramo en mayúsculas (2 casos, 3 funciones) en Artistic Metropol (2). Pasarlos por run._fix_caps. Por ejemplo: 24/11 20:00: «ESTUDIOS DE CINE Noviembre 2026 con Alejandro Mucientes»; 26/11 12:00: «VIRGINIA WOOLF: NOCHE Y DÍA V.O.S.E. Sesión Teta»
- Directores de relleno («Desconocido», «Varios») (3 casos, 5 funciones) en Cineteca Madrid (3). Mejor vacío. Por ejemplo: «CIMA Proyecta: 25-N Cortos contra las violencias»: «Varias autoras»; «Escáner - Sesión de cortometrajes»: «Varios autores»
- Directores que empiezan con «de» (1 caso) en Embajadores Glorieta. Limpiar en el scraper. Por ejemplo: «Ciclo de Cine Peruano: Reinas»: «de Klaudia Reynicke, Diego Vega»
- Dos títulos en el mismo horario: Cines Princesa ×48, Golem Madrid ×17, Renoir Plaza de España ×17, Cines Ideal ×12, Artistic Metropol ×5, Cineteca Madrid ×5, Renoir Retiro ×5, Embajadores Ercilla ×4, Embajadores Glorieta ×2. Ejemplo (Cines Princesa): 2026-11-24 15:50: 'El Director' vs 'La bola negra'
- 15 funciones sin director: Cines Callao (15/24).
- 15 funciones sin link de Letterboxd: Cines Callao (15/24).
- 13 títulos sin ningún dato (ni director, ni año, ni duración, ni Letterboxd): puede que no sean películas. Cineteca Madrid: «Capítulo XXXVI: Carta blanca a María Castro y Álvaro Cáceres», «Cuando el guion impulsa la tecnología: Seminario impartido por Priit y Olga Pärn» y 6 más; Artistic Metropol: «ESTUDIOS DE CINE Noviembre 2026 con Alejandro Mucientes»; Sala Equis: «Vespertine-björk»; Cines Callao: «Salta Conmigo»; Cine Estudio: «Screening LAV #36. No vi que se movieran los pétalos»; Embajadores Ercilla: «El Apartamento».

## Tablero de fuentes

Cómo viene cada sala: funciones publicadas, hasta qué día llega su programación, cuántas tenía hace una semana, cuántos de los últimos días contestó su fuente, y una barrita por día de las últimas cuatro semanas.

### Buenos Aires

| Sala | Func. | Títulos | Hasta | Hace 7 días | Fuente | Cuatro semanas |
|---|---:|---:|---|---:|---|---|
| 🟢 Atlas Caballito | 122 | 106 | 29/11 | 254 | a mano | `____________________████▇▇▆▅` |
| 🟢 Sala Lugones | 47 | 26 | 13/12 | 65 | 7 de 7 días | `▄▄▄▃▃████▇▇▇▆▆▆▇▇▇▆▆██▇▇▇▆▆▆` |
| 🟢 Cine Gaumont | 32 | 15 | 2/12 | 54 | 7 de 7 días | `██▇▆▅▄▄█▇▆▅▄▄▃▃▇▇▆▅▄▄▅██▇▅▅▄` |
| 🟢 Cacodelphia | 29 | 14 | 17/12 | 31 | 7 de 7 días | `▃▇▆▆▅▄▃▂██▇▇▆▅▄▇▇▆▆▅▄▄█▇▇▇▆▅` |
| 🟢 Universidad del Cine | 26 | 26 | 27/11 | 26 | a mano | `___________________█████████` |
| 🟢 Cine York | 23 | 23 | 29/11 | 33 | 7 de 7 días | `▄███▇▇▇▇▇██▇▇▇▇▇▇▇▆▆▆▆▆▆▆▅▅▅` |
| 🟢 Cine Cosmos | 16 | 6 | 25/11 | 16 | 7 de 7 días | `▃▂█▇▆▅▄▃▂▆▅▄▃▂▂▂█▇▆▅▄▃▂█▇▆▅▄` |
| 🟢 MALBA | 15 | 14 | 5/12 | 28 | 7 de 7 días | `▃▄▄▇▇▆▆▇███▇▇▆▆▆▆▆▅▅▅▅▅▅▄▄▃▃` |
| 🟢 Amorina | 10 | 8 | 24/12 | 17 | 7 de 7 días | `███▇▇▇▇██▇▇▇▇▇▇▆▆▆▆▆▆▆▆▅▅▄▄▄` |
| 🔴 Sala Lúcida | 9 | 7 | 28/11 | 22 | 7 de 7 días | `▄▄▄▄▄▄▄▄▄▄▄▄▅▅▅▅▅▅▅███▇▇▇▆▅▄` |
| 🟢 Centro Cultural 25 de Mayo | 8 | 8 | 3/12 | 9 | 7 de 7 días | `▂▂▄▄▅▅▅▅▅▅▅▅▅▅▅▅▅▄▄_████▇▇▇▇` |
| 🟡 Casa del Bicentenario | 7 | 7 | 29/11 | 9 | a mano | `████▇▅▂▂▂▂▂▂_______▆▆▆▆▆▆▆▆▅` |
| 🟢 Cinema Club Lomas de Zamora | 6 | 6 | 29/11 | 0 | 6 de 6 días | `______________________█▇▆▆▆▅` |
| 🟢 Cinema Club Recoleta | 6 | 5 | 30/11 | 0 | 6 de 6 días | `______________________█▇▇▆▇▆` |
| 🟢 Club Lucero | 6 | 6 | 27/11 | 0 | 6 de 6 días | `__█▄__________________▃▃▂▂▂▂` |
| 🟢 Hasta Trilce | 6 | 1 | 8/12 | 8 | 7 de 7 días | `▆▆▆▆▆▆▆▆▅▆▆▆▆▆█▆▆▆▆▆██▆▆▆▆▆▆` |
| 🔴 CCK | 5 | 5 | 29/11 | 9 | caída hace 10 días | `▂▅███▇▆▆▆▆▆▆▆▆▆▆▆▆▆▄▄▄▄▄▄▄▃▃` |
| 🔴 Centro Cultural Borges | 5 | 5 | 13/12 | 14 | caída hace 10 días | `▃▃█▇▆▃▃▃▃▃▃▃▃▃▃▃▃▂▂▂▂▂▂▂▂▂▁▁` |
| 🔴 Espacio INCAA Morón | 5 | 5 | 29/11 | 0 | 6 de 6 días | `______________________█▇▇▅▅▅` |
| 🟢 Filo Cine | 5 | 5 | 3/12 | 10 | 7 de 7 días | `▅▄▇▇▇▇▇▇▇▇▇▇▇▇██▇▇████▇▇▆▅▅▅` |
| 🟢 Centro Cultural Munro | 4 | 4 | 6/12 | 9 | 7 de 7 días | `▂▇▇▇▇▇▆▆▆████▇▇▆▆▆▆▆▅▅▅▅▅▄▄▃` |
| 🟢 Cineclub Farus | 4 | 4 | 27/11 | 5 | 7 de 7 días | `▄▄_________________████████▇` |
| 🟢 Cinema Club Palermo | 4 | 4 | 29/11 | 0 | 6 de 6 días | `______________________█▇▇▆▅▄` |
| 🟢 Biblioteca Nacional | 3 | 3 | 15/12 | 1 | 7 de 7 días | `▆▆▆▆▆▆▆▆▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃_███` |
| 🟢 Casa de la Lectura y la Escritura | 3 | 3 | 10/12 | 0 | 5 de 5 días | `_______________________▆████` |
| 🟢 Centro Cultural Recoleta | 3 | 3 | 29/11 | 11 | 7 de 7 días | `▃▅▆▇▇▆▅▅▅▅▅▆▆▅▅▅▅▅▄█▇▇▇▇▆▅▄▃` |
| 🟡 La Tomada | 3 | 3 | 28/11 | 17 | a mano | `___________________█████████` |
| 🟡 Arthaus | 2 | 2 | 29/11 | 9 | 7 de 7 días | `▂▂▂▂▂▂▂▂▂▄▄▄▄▄▄▄▄▄▃█▇▇▇▇▇▆▄▂` |
| 🟢 Bellas Artes | 2 | 2 | 28/11 | 3 | 7 de 7 días | `████▇▅▅▅▅▅▅▃____▇▇▆▅▅▅▅▅▅▅▃▃` |
| 🟢 Biblioteca del Congreso | 2 | 2 | 26/11 | 4 | 7 de 7 días | `▃▂▂_██████▇▇▇▇▇▇▇▆▆▆▆▆▅▅▃▃▃▃` |
| 🟢 CEA | 1 | 1 | 27/11 | 0 | 6 de 6 días | `______________________██▆█▆▃` |
| 🟢 Cine Helios | 1 | 1 | 24/11 | 0 | 6 de 6 días | `______________________█▃▃▃▃▃` |
| 🟢 Cineclub Turdera | 1 | 1 | 27/11 | 0 | 6 de 6 días | `______________________███▅▅▅` |
| 🟢 Lumiton | 1 | 1 | 25/11 | 2 | 7 de 7 días | `████▆▆▆▆▆▅▅▆▆▆▆▆▆▆▆▅▅▅▅▅▅▅▃▃` |
| 🟢 Museo del Cine | 1 | 1 | 29/11 | 1 | a mano | `___________________█████████` |
| 🔴 Centro Cultural de la Cooperación | 0 | 0 |  | 1 | 2 de 2 días | `██_▆▆▆▆▆▆▅▅▅▅▅▅▅▃▃___▃▃_____` |
| 🟢 Hoyts Abasto | 431 | 16 | 29/12 | 677 | 7 de 7 días | `▅█▇▇▆▆▆▅▇█▇▇▆▆▅██▇▇▆▆▇▇▇▆▆▆▅` |
| 🟢 Cinemark Palermo | 348 | 13 | 23/12 | 608 | 7 de 7 días | `▅█▇▇▆▆▅▅▇█▇▇▆▆▆███▇▇▆▇▇▇▆▆▆▅` |
| 🟢 Hoyts Dot | 330 | 14 | 29/12 | 383 | 7 de 7 días | `▅█▇▇▇▆▅▅▇▇▇▆▆▆▅▅█▇▇▆▆▅▆▆▆▆▅▅` |
| 🟢 Cinemark Puerto Madero | 291 | 12 | 29/12 | 337 | 7 de 7 días | `▅██▇▇▆▆███▇▇▆▆▆███▇▇▆▆▇▇▇▆▆▅` |
| 🟢 Multiplex Pilar | 289 | 17 | 23/12 | 594 | 7 de 7 días | `▇▇▆▆▅▅▄▄▇▆▇▆▆▅██▇▇▆▆▅▇▇▆▆▅▅▄` |
| 🟢 Multiplex Lavalle | 267 | 15 | 23/12 | 476 | 7 de 7 días | `█▇▇▆▆▆▅▇▇▆▇▆▆▅███▇▇▆▆▇▇▇▇▆▆▅` |
| 🟢 Multiplex Belgrano | 240 | 16 | 23/12 | 545 | 7 de 7 días | `█▇▇▆▆▅▄█▇▇▇▆▆▅▄██▇▆▆▅█▇▆▆▅▅▄` |
| 🟢 Multiplex Canning | 234 | 12 | 23/12 | 291 | 7 de 7 días | `▆█▇▇▇▆▆█▇▇▇▇▆▆███▇▇▆▆▅▇▆▆▆▅▅` |
| 🟢 Cinemark Caballito | 191 | 12 | 29/12 | 214 | 7 de 7 días | `▅█▇▇▆▆▅▅▇█▇▇▆▆▅██▇▇▆▆▅▆▇▆▆▅▅` |
| 🟢 Cines Pixel | 39 | 11 | 2/12 | 40 | 7 de 7 días | `____________________▄▃██▇▆▅▄` |

Sin funciones y sin nada que marcar (salas de festival o que programan cada tanto): Avalon (desde el 21/11), Centro Cultural Leopoldo Marechal (desde el 8/11), Cine Lorca (desde el 23/11), Escuela Da Vinci (desde el 31/10), FADU (desde el 7/10), LABA (desde el 17/11), Museo Moderno (desde el 25/10), Sala Mario Soffici (desde el 21/8), Cinépolis Houssay (desde el 23/11), Cinépolis Recoleta (desde el 23/11), Showcase Belgrano (desde el 23/11).

### Madrid

| Sala | Func. | Títulos | Hasta | Hace 7 días | Fuente | Cuatro semanas |
|---|---:|---:|---|---:|---|---|
| 🔴 Cines Ideal | 210 | 29 | 19/1 | 30 | caída hace 1 día | `▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂█▇` |
| 🟢 Cines Princesa | 111 | 27 | 26/11 | 0 | 6 de 6 días | `▄███▇▆▅▄█▇▇▇▆▅▄▃▂_____███▇▆▅` |
| 🟢 Cineteca Madrid | 78 | 64 | 3/1 | 47 | 7 de 7 días | `▄▆▅▇▇▆▆▆▆▆▅▅▅▅▅▅▅▆▅▅▅▅▆██▇▇▇` |
| 🟢 Renoir Plaza de España | 57 | 8 | 26/11 | 0 | 6 de 6 días | `▄███▇▆▅▄███▇▆▅▄▃▂_____███▇▆▅` |
| 🟢 Golem Madrid | 49 | 11 | 26/11 | 53 | 7 de 7 días | `▄▇▇▇▆▅▄▄▇▇▇▇▆▅▃▇▇█▇▆▅▄██▆▇▆▅` |
| 🟢 Embajadores Glorieta | 47 | 26 | 27/12 | 55 | 7 de 7 días | `▄█▇▇▆▅▄▄▇▇▇▇▆▅▄▇▇▇▇▆▅▅██▇▆▅▅` |
| 🟢 Embajadores Ercilla | 45 | 32 | 22/12 | 53 | 7 de 7 días | `▄█▇▇▆▅▄▄██▇▇▆▅▄█▇▇▆▆▅▅█▇▇▆▅▅` |
| 🟢 Renoir Retiro | 36 | 8 | 26/11 | 0 | 6 de 6 días | `▄███▇▆▅▄▇▇▇▇▆▅▄▃▂_____███▇▆▅` |
| 🟢 Cine Doré | 28 | 28 | 16/12 | 46 | 7 de 7 días | `▃▂▂▇▇██▂▂▂▂▂████▇▇▆▆▆▆▆▅▅▅▄▄` |
| 🟢 Cines Callao | 24 | 4 | 20/12 | 6 | 7 de 7 días | `▃█▇▆▅▅▄▃▇▇▇▅▄▃▂█▆▆▅▄▃▂▁▇▇▆▆▅` |
| 🟢 Cine Estudio | 19 | 16 | 3/12 | 17 | 7 de 7 días | `▄▅▆▆▅▅▄▄▄██▇▇▆▆▆▆▅▅▄▄▄▄▆▆▅▅▅` |
| 🟢 Artistic Metropol | 18 | 12 | 26/11 | 25 | 7 de 7 días | `▅▅▆▅▅▅▅▅▅▇▇▆▅▆▅█▇▆▅▅▅▄▇▆▅▅▅▄` |
| 🟢 Sala Equis | 12 | 8 | 29/11 | 28 | 7 de 7 días | `____██▇▇▇▇▇▆▆▆▆▆▆▅▅▅▄▄▄▄▄▃▃▂` |
| 🟢 Museo Reina Sofía | 8 | 8 | 12/12 | 14 | 7 de 7 días | `████▇▇▇▇▇▇▇▆▅▅▅▅▅▄▃▃▆▆▆▆▅▅▄▄` |

---

Generado por `scripts/audit.py`. Para correrlo a mano: `cd ~/cines && python3 scripts/audit.py`. Para que los agentes revisen y arreglen lo que encontró: `/auditoria` en Claude.
