# Si te digo: manual de marca para Instagram

Este manual existe para que cualquier pieza nueva salga igual a las anteriores.
No se diseña cada vez: se elige una de cuatro plantillas, se escribe el texto y
el generador pone las medidas. Los números viven en `marca/marca.css`; si este
manual y la hoja de estilos se contradicen, manda la hoja.

## Cómo se hace una pieza

1. Escribir una ficha JSON (ver `marca/ejemplos/`).
2. `python3 scripts/pieza.py marca/piezas/<nombre>.json`
3. Los PNG quedan en `posts/piezas/<nombre>/<formato>/slide-N.png`.
4. Mostrárselos a Mateo antes de publicar. Nada sale sin su visto bueno.

El generador corta con error si el texto usa un signo prohibido o no entra.
Cuando no entra, se acorta el texto o se parte en otro slide. Nunca se achica
la letra, se aprietan márgenes ni se agrega un tamaño nuevo.

## Principios

- Fondo negro, texto gris claro, un solo color de acento por pieza.
- Todo alineado a la izquierda y arriba. El aire queda abajo.
- Sin fotos, sin ilustraciones, sin degradés, sin sombras, sin íconos, sin emojis.
- En el centro de un anuncio de festival va **el logo del festival**, siempre el que ya
  usa la web: el generador lo saca de `data/festivales.json` con el slug (`"festival":
  "rojo-sangre"` en la ficha). Va en círculo, como en la web. Nunca se busca ni se
  dibuja otro: si el festival no tiene logo en la web, se carga ahí primero.
- La mano con el ojo (`logo.png`) va en el centro sólo cuando el anuncio no es de un
  festival. Siempre el original, sin recolorear. La firma de cada pieza es `sitedigo.com`.
- La cabecera con rótulo, la bajada de color y las rayas son de la programación
  (cartelera y listas). Un anuncio no las lleva: va centrado y con el logo.
- Si hay dudas entre poner algo y no ponerlo, no se pone.

## Formatos

| | Story | Post (feed) |
|---|---|---|
| Lienzo | 1080 x 1920 | 1080 x 1350 |
| Margen arriba / costados / abajo | 130 / 90 / 100 | 80 / 70 / 70 |
| Ancho de columna | 900 | 940 |

No hay formato cuadrado ni apaisado. Un carrusel son varios posts de 1080 x 1350
con la misma cabecera y la misma firma; el contador (`2/5`) va a la derecha. Máximo 10.

## Estructura fija

Toda pieza tiene tres partes, siempre en este orden:

1. **Cabecera.** Rótulo en mayúsculas (qué es: `SALA NUEVA`, `AVISO`, `ESTA SEMANA`,
   `CARTELERA DE CINES`), hasta 20 caracteres. Debajo la bajada en minúsculas y en el
   color de acento (de qué se trata), hasta 26. Una línea cada una. Debajo, raya de
   2 px del color de acento.
2. **Cuerpo.** Una de las tres plantillas.
3. **Firma.** La misma en todas las piezas, sin excepción, también en la cartelera
   diaria. Ver abajo.

## La firma (el pie)

`sitedigo.com` cierra todas las piezas y es siempre idéntico. No se cambia de lugar, de
tamaño ni de peso por ningún motivo, y no hay pieza que no lo lleve.

| | Story | Post |
|---|---|---|
| Posición | centrado, borde de abajo del texto a 100 del borde del lienzo | centrado, a 70 |
| Tamaño | 28 | 24 |
| Peso | 600 | 600 |
| Color | texto `#e0e0e0` | texto `#e0e0e0` |
| Interletra | 0.02em | 0.02em |
| Aire mínimo arriba | 40 | 32 |

- Sin raya encima, sin color del día, sin texto a la izquierda.
- **Contador**: cuando hay más de un slide va `2/12` a la derecha, en la misma línea,
  mismo tamaño, peso 400, gris. Como va en su propia columna, no corre a `sitedigo.com`
  del centro.
- Los valores viven en `.firma` de `marca/marca.css` y, repetidos, en `.post-footer` de
  `instagram.html` (la cartelera diaria). Si se toca uno se toca el otro.

## Plantillas

- **centrada**: para anunciar (un festival cargado, una sala nueva, una novedad). Sin
  cabecera, sin rayas y sin color del día. Todo centrado: arriba de todo un mini título
  opcional en mayúsculas chicas (`NUEVOS FESTIVALES EN LA WEB`, hasta 34 letras, del
  mismo tamaño que `sitedigo.com`), después un antetítulo y el
  nombre en grande, el logo en el medio, abajo hasta tres líneas de datos (la primera
  más grande, las otras en gris) y la firma. Es la plantilla por defecto
  para cualquier comunicación que no sea programación.

  | | Story | Post |
  |---|---|---|
  | Antetítulo | 40 | 36 |
  | Nombre (bold) | 72 | 64 |
  | Logo de festival, diámetro | 380 | 320 |
  | Logo de Si te digo, alto | 600 | 460 |

  El logo es opcional: con `"logo": false` en el slide no va ninguna imagen y el anuncio
  y los datos quedan juntos en el centro (así salió la story del newsletter).

  **Íconos.** Arriba del titular puede ir un dibujo de línea, en el verde de la web:
  `"icono": "mail"` pone un sobre (150 de ancho en story, 120 en post). Son dibujos del
  generador (`ICONOS` en `scripts/pieza.py`), nunca emojis: un emoji cambia de dibujo
  según el aparato y trae colores que no son de la marca. Uno por pieza como mucho.

  **Verde de la web.** En la centrada, el ícono y el link al que se invita a entrar van en
  el verde de sitedigo (`#00d060`): en la ficha el link se marca `*sitedigo.com/newsletter*`.
  Nada más va en verde, y la firma de abajo no cambia nunca de color.
  | Primer dato | 40 | 36 |
  | Datos en gris | 28 | 24 |
  | Mini título (500, +0.08em) y sitedigo.com (600) | 28 | 24 |

- **frase**: una sola oración grande, con una nota chica opcional. Para anunciar algo
  en una línea. Hasta unas 90 letras.
- **texto**: titular, uno a tres párrafos y nota opcional. Para explicar.
- **lista**: filas iguales a las de la cartelera: clave a la izquierda (hora o número),
  etiqueta, título, secundario y nota. Hasta 5 filas en story y 4 en post.

No se inventan plantillas nuevas para una pieza. Si algo no entra en estas cuatro, se
conversa con Mateo y se agrega al sistema para todas.

## Tipografía

Una sola familia: **DejaVu Sans** (la que ya se ve en las stories de la cartelera),
en regular y bold. Sin cursivas salvo el título alternativo de una película.

| Rol | Story | Post | Peso | Caja | Color |
|---|---|---|---|---|---|
| Rótulo | 64 | 56 | 700 | MAYÚSCULAS | texto |
| Bajada | 56 | 48 | 700 | minúsculas | acento |
| Frase | 80 | 72 | 700 | minúsculas | texto |
| Titular | 56 | 48 | 700 | minúsculas | texto |
| Párrafo, título de fila | 40 | 32 | 400 / 500 | minúsculas | texto |
| Clave (hora, número) | 52 | 44 | 700 | cifras tabulares | texto |
| Secundario | 28 | 22 | 400 | minúsculas | texto al 85 % |
| Nota | 22 | 16 | 400 | minúsculas | gris |
| Firma (`sitedigo.com`) | 28 | 24 | 600 | minúsculas | texto |
| Contador | 28 | 24 | 400 | cifras tabulares | gris |
| Etiqueta | 18 | 14 | 500 | MAYÚSCULAS, +0.06em | gris o color de sala |

Interlineado: 1 a 1.1 en lo grande, 1.3 en párrafos, 1.4 en notas.

## Espaciado

Sólo existen estos valores (story / post):

| Entre | px |
|---|---|
| Las dos líneas de la cabecera | 14 |
| Cabecera y su raya | 36 / 32 |
| Raya y cuerpo | 34 / 24, más 30 / 20 en frase y texto |
| Bloques del cuerpo (titular, párrafos, nota) | 40 / 32 |
| Filas de una lista | 30 / 20 arriba y abajo, raya de 1 px entre filas |
| Columna de la clave y su separación | 160 + 32 / 130 + 22 |
| Líneas dentro de una fila | 10 / 8 |
| Cuerpo y firma, como mínimo | 40 / 32 |

## Color

| Uso | Valor |
|---|---|
| Fondo | `#0a0a0a` |
| Texto | `#e0e0e0` |
| Gris (notas, contador) | `#666666` |
| Rayas finas | `#2a2a2a` |

**Acento: el del día en que se publica**, igual que la cartelera diaria. Sólo en frase,
texto y lista; la centrada no lleva acento.

| Domingo | Lunes | Martes | Miércoles | Jueves | Viernes | Sábado |
|---|---|---|---|---|---|---|
| `#b86b52` | `#5f7fa6` | `#b79a58` | `#8b74a8` | `#5f9b7f` | `#b06d86` | `#5f9c96` |

El acento va en tres lugares y en ninguno más: la bajada, la raya de la cabecera y, como
mucho, una palabra resaltada por slide (`*así*` en la ficha). La firma no lleva acento.
El verde `#00d060` de la web se usa sólo en la centrada, para el ícono y un link.

Las etiquetas de sala llevan el color que esa sala tiene en la web. Una etiqueta que
no es una sala va en gris.

## Escritura

- Minúsculas en todo, también en nombres propios y títulos. Mayúsculas sólo en el
  rótulo y las etiquetas (las pone la hoja de estilos; en la ficha se escribe normal).
- **Nunca el punto medio (·)**, ni viñetas, ni rayas largas o cortas (— –). Para
  separar: coma, punto, salto de línea o `/` en el número de slide. `2026, 118 min`.
- Sin emojis ni banderas. Sin signos de exclamación dobles. Sin hashtags en la imagen.
- Voseo rioplatense, frases cortas, sin adjetivos de venta. Se dice el dato y dónde verlo.
- Horas en 24 h con dos puntos: `19:30`. Fechas: `jueves 19 de noviembre`.
- La dirección siempre es `sitedigo.com`, sin `www` ni `https`.

## Receta: anuncio de festival nuevo

Es el estilo que Mateo aprobó y publicó el 18/11/2026 (Buenos Aires Rojo Sangre e
Infinito Super 8). Se repite igual cada vez que se carga un festival:

- **Una pieza por festival.** Ni portada aparte ni carrusel.
- Plantilla `centrada`, con `"festival": "<slug>"` para que tome el logo de la web.
- Mini título: `nuevos festivales en la web`.
- Antetítulo: `ya está la cartelera del` (o `de la`, `de`, según el nombre).
- Titular: el nombre del festival, sin edición ni año.
- Líneas: primero las fechas (`del 19 al 29 de noviembre`), después las sedes y, si
  corresponde, `entrada gratis`. Fechas y sedes salen de `data/festivales.json` y de las
  funciones cargadas en `data/cartelera.json`, no de memoria.
- Fichas de referencia: `marca/piezas/rojo-sangre.json` e `infinito-super-8.json`.

## Cómo se publica

Las stories de piezas las publica `post-pieza.yml` en GitHub (el token de Instagram
sólo está ahí). Con el visto bueno de Mateo:

1. Commitear y pushear las PNG de `posts/piezas/<pieza>/story/`.
2. En otro push, agregar un pedido `posts/piezas/pedidos/<fecha>-<nombre>.json`:
   `{"stories": ["posts/piezas/<pieza>/story/slide-1.png", ...]}`, en el orden en que
   tienen que salir.
3. El workflow publica cada pedido una sola vez (lock en el tag
   `ig-posted/pieza/<nombre>` y marca `.posteado` al lado del pedido).

Si la cartelera del día todavía no salió, el pedido espera y sale cuando termina el
posteo diario: una pieza publicada antes haría que la cartelera de ese día no saliera.
Los posts del feed todavía se suben a mano.

## Cómo pedirlo

Con decir qué se quiere comunicar alcanza. Por ejemplo:

> Armá una story y un post avisando que sumamos el Club Lucero. Sale el jueves.

Quien arma la pieza elige la plantilla, escribe la ficha en `marca/piezas/`, corre el
generador, muestra los PNG y espera el visto bueno.

## Pendientes conocidos

- En la Mac las piezas salen en Verdana porque DejaVu Sans no está instalada. Son casi
  iguales pero no idénticas. Se arregla copiando los TTF a `marca/fonts/`.
