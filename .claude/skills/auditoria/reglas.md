# Reglas de la casa

Para cualquiera que toque la cartelera: el orquestador de `/auditoria` y cada
agente de `.claude/agents/`. Son decisiones que ya se tomaron, casi todas
después de un error que salió a la web. No se rediscuten en cada corrida.

## Dónde y cómo se trabaja

- **En un worktree sobre `origin/main`**, nunca en el checkout principal: ahí
  puede haber otra sesión trabajando. `git worktree add -b tmp/<algo> <dir> origin/main`.
- **No correr `run.py` en la máquina local.** Pisa `data/cartelera.json` con lo
  que se pueda scrapear desde ahí, y desde afuera de Argentina varias fuentes
  no contestan: las salas que fallan desaparecen del archivo. La web la publica
  GitHub Actions. Para probar un scraper se importa la función suelta:
  `python3 -c "import sys; sys.path.insert(0, '.'); import scraper; print(scraper.scrape_bn())"`.
- **El scraper se prueba contra la página real**, no contra lo que uno cree
  que dice. Guardar el HTML en el scratchpad y correr sólo el parser. Si el
  sitio bloquea desde esta máquina (403, Cloudflare), decirlo: no se da por
  bueno un arreglo que no se pudo probar.
- **Arreglar el scraper y también el dato publicado.** Pushear `scraper.py` no
  cambia la web hasta el próximo scrape (madrugada y tarde, hora argentina).
  Si algo tiene que verse hoy, se corrigen las filas en `data/cartelera.json`
  (o `cartelera-madrid.json`): los 14 campos de `run.py` en su orden, título,
  director y ciclo pasados por `run._fix_caps`, orden sólo por (fecha, hora)
  con sort estable, `fuentes[<sala>]` al día, `json.dumps(..., ensure_ascii=False,
  indent=2)` y sin salto de línea final. Si el diff tiene miles de líneas, el
  orden quedó mal.

## Qué va en cada casillero

El reglamento es `categorias.py`. En corto:

- **Título**: una película, o un programa con nombre propio. Nunca el nombre
  de un ciclo, de un festival, una charla, un taller o un torneo. Sin el
  director, el año, la versión (VOSE, 35 mm) ni el ciclo pegados.
- **Ciclo**: un ciclo, un festival o su sección ("Festival FIDBA - Órbita").
  No es un género ("Documental"), ni un tipo de actividad ("Cine"), ni el
  mismo título. "Estreno" y "Continúa" se aceptan: las salas los usan así.
- **Director**: personas. Vacío si no se sabe: nunca "Desconocido" ni "Varios".
- **Sala**: una que la web conoce (`index.html`: chip y dirección), en la
  cartelera de su ciudad. Madrid va en `cartelera-madrid.json`.
- **Festivales de otra ciudad** (Mar del Plata): en su propio archivo, nunca
  en `cartelera.json`. Los del conurbano sí van a la grilla.

## Lo que no se negocia

- **Mejor vacía que equivocada.** Una función sin director, año ni Letterboxd
  se acepta; con la ficha de otra película, no. No se relajan las reglas del
  enrichment para "mejorar la cobertura".
- **Letterboxd verificado.** Un slug entra sólo si la página abre, el director
  coincide y el título es ese. Ante la duda, vacío. Con cortos y películas del
  mismo director, comparar también el título.
- **Nada gritado.** Ni títulos, ni directores, ni ciclos en mayúsculas.
- **Ninguna bandera** (emoji) en ningún campo.
- **Los datos de la fuente no se "mejoran"**: si un título trae un guion largo
  desde el cine, queda. Lo que se arregla es lo que está en el casillero
  equivocado o mal leído.
- **Los logos son los originales**, nunca una imitación.

## Qué se decide solo y qué se pregunta

Se hace sin preguntar: arreglar un scraper, desagregar un programa doble,
descartar una actividad que no es cine, cargar la grilla de un festival que
ya está en `data/festivales.json`, completar una ficha verificada, actualizar
`data/festivales_radar.json` con fechas confirmadas.

Se deja listo y se le pregunta a Mateo: sumar una sala nueva a la web, sumar
un festival nuevo al registro, sacar una sala, cambiar cómo se ve algo en
`index.html`, y cualquier cosa de Instagram. También una excepción en
`data/audit_excepciones.json` que no sea obvia: una excepción es decir "esto
está bien así", y eso lo dice él.

## Cómo se cierra

- Los tests que tocan lo cambiado, más los cuatro de siempre:
  `python3 test_categorias.py && python3 test_audit_agentes.py && python3 test_ciclos_mayusculas.py && python3 test_banderas.py`.
- Un comentario dice por qué, no qué. En castellano, sin punto medio ni guion
  largo.
- El commit dice qué estaba roto y por qué. Se pushea a `main` (los workflows
  corren desde ahí): `git push origin HEAD:main`, con `git push --dry-run` antes.
- Después se vuelve a correr `python3 scripts/audit.py` y se confirma que el
  hallazgo ya no sale. Lo que no se pudo arreglar se dice, con el motivo.
