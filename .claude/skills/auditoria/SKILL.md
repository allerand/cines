---
name: auditoria
description: Auditoría de la cartelera de sitedigo.com con agentes. Corre scripts/audit.py (salas caídas o viviendo de caché, datos en el casillero equivocado, festivales desatendidos, fichas incompletas), reparte cada hallazgo al agente que le corresponde para que lo confirme contra la fuente, aplica los arreglos de a uno, los hace verificar y publica. Usar cuando el usuario pida revisar o auditar los cines, mirar qué falta, actualizar los festivales, ordenar las categorías, cuando llegue el mail de la auditoría o del centinela, o invoque /auditoria.
---

# Auditoría de la cartelera

Objetivo: que mantener la web cueste poco y que nada se pierda. Cada scraper
de `scraper.py` atrapa sus excepciones y devuelve `[]`, así que **cuando una
fuente cambia, la sala desaparece de la web sin que nada falle**. Y cuando un
scraper lee mal, publica un ciclo donde va una película sin que nadie lo vea.

## Cómo está armado

Tres anillos, del que frena al que arregla:

1. **El portero**, en cada scrape (`run.py`, reglas en `categorias.py`). No
   deja publicar lo que es seguro que no es una película: un título que es el
   nombre de un ciclo de esa sala o de un festival del registro. Lo que frena
   queda en `cartelera.json` bajo `retenidas`.
2. **Los cinco agentes del script** (`scripts/audit.py`), todos los lunes con
   informe por mail y todos los días en modo centinela (sólo avisa de lo
   grave que ayer no estaba). Detectan; no leen la fuente con criterio.
3. **Los agentes de Claude** (`.claude/agents/`), que coordina este skill:
   confirman cada hallazgo contra la fuente y dejan el arreglo escrito.

Cada área tiene un solo dueño, con el mismo nombre en el script y acá:

| Área | Qué cuida | En el script | Agente de Claude |
|---|---|---|---|
| frescura | que el scrape corra y las stories salgan | `check_frescura`, `check_stories`, `check_corridas` | lo mira quien orquesta |
| fuentes | que ninguna sala se caiga, se quede corta o viva de caché | `check_cobertura`, `check_rendimiento`, `audit_fuentes.py` | `auditor-fuentes` |
| categorias | que cada dato esté en su casillero | `check_categorias`, `categorias.py` | `auditor-categorias` |
| festivales | que ninguno se pase y sigan al día | `check_festivales`, `audit_festivales.py` | `monitor-festivales` |
| fichas | director, año, Letterboxd, entradas | `check_calidad`, `check_completitud` | `auditor-fichas` |
| (todas) | que nada salga sin una segunda mirada | los tests | `verificador` |

Las reglas que valen para todos están en `reglas.md`, al lado de este
archivo. Leelas antes de empezar.

## 1. Preparar

```bash
git -C ~/cines fetch -q origin
git -C ~/cines worktree add -b tmp/auditoria-$(date +%m%d) "$SCRATCH/wt" origin/main
```

`$SCRATCH` es el scratchpad de la sesión. Todo lo que sigue se hace en ese
worktree: en `~/cines` puede haber otra sesión trabajando.

## 2. Correr el script

```bash
python3 scripts/audit.py --json "$SCRATCH/audit.json" --out "$SCRATCH/audit.md"
```

Así, con `--json` apuntando afuera de `data/`, no toca la memoria del
repositorio (eso lo hace el workflow). `data/audit.json`, el del último
lunes, dice desde cuándo está abierto cada hallazgo. Con `--offline` saltea
la red; con `--como-si-fuera 2026-11-15` audita la cartelera de ese día.

Leé `audit.md` entero y después `audit.json`: `hallazgos` (cada uno con
`agente`, `ciudad`, `cine`, `regla`, `msg`, `desde`, `nuevo`, `ejemplos`),
`tablero` (una fila por sala) y `partes`. Si en `partes` algún agente tiene
`caido`, eso va primero: lo que no se revisó no pasa por revisado.

## 3. Repartir

Armá la lista de trabajo: todos los hallazgos `ERROR`, más los `AVISO` que
sean del mismo problema. Primero lo nuevo, después lo que sigue abierto hace
más tiempo. Agrupá por sala: una sala con tres hallazgos es un solo encargo.

Lanzá los agentes **en paralelo**, uno por sala (o por grupo de salas que
comparten fuente, como las tres Renoir), con el agente que corresponde al
`agente` del hallazgo. Si una sala tiene hallazgos de fuentes y de
categorías, primero fuentes: una sala caída no tiene categorías que ordenar.
`monitor-festivales` va una sola vez, con todos los hallazgos de festivales.

A cada agente pasale: la ruta del worktree, sus hallazgos copiados de
`audit.json` (con los `ejemplos`), la fila de la sala en `tablero`, y que su
informe tiene que seguir el formato de su archivo. Si el tipo de agente no
aparece en la lista disponible (pasa cuando la sesión no arrancó en el
repo), lanzá uno de propósito general y dale como instrucciones el contenido
de `.claude/agents/<nombre>.md`.

**Los agentes investigan y proponen; no editan.** `scraper.py` es un solo
archivo de más de doce mil líneas: si varios lo tocan a la vez, se pisan.

## 4. Aplicar, de a uno

Por cada informe, en orden de gravedad:

1. Aplicá el arreglo en el worktree. Si el agente dijo "no se pudo probar
   desde acá", probalo vos o dejalo afuera.
2. Corregí el dato publicado si hace falta que se vea hoy (ver `reglas.md`).
3. Lanzá el `verificador` con el diff y el hallazgo. Con "NO PASA" se corrige
   o se saca; no se discute con el verificador, se le hace caso o se le
   muestra en la fuente por qué está equivocado.
4. Un commit por arreglo, con qué estaba roto y por qué.

Lo que el agente marcó "PARA MATEO" no se aplica: va al informe final.

## 5. Cerrar

- Actualizá `data/festivales_radar.json` con lo que confirmó el monitor
  (cada fecha con su fuente) y `data/audit_excepciones.json` con lo que se
  decidió dejar como está (cada una con su motivo).
- Volvé a correr el script y compará: qué hallazgos se cerraron, cuáles
  siguen, si apareció alguno nuevo por los cambios.
- Tests: los de cada archivo tocado más
  `python3 test_categorias.py && python3 test_audit_agentes.py && python3 test_audit_cobertura.py && python3 test_ciclos_mayusculas.py && python3 test_banderas.py`.
- `git push --dry-run origin HEAD:main` y después el push de verdad. La web
  sirve el JSON nuevo en un minuto: se comprueba pidiendo
  `sitedigo.com/data/cartelera.json` con un parámetro que evite el caché.

## 6. Contarle a Mateo

Corto y en este orden:

1. **Qué se arregló**, sala por sala, con lo que se ve distinto en la web.
2. **Qué necesita una decisión suya**, cada cosa como una pregunta que se
   contesta con sí o no (sumar el festival X: 180 funciones en una sala que
   la web no tiene; dar de baja la sala Y que no programa hace dos meses).
3. **Qué quedó sin arreglar y por qué** (la fuente bloquea, no se pudo
   verificar).
4. **Qué viene**: festivales de las próximas semanas según el radar.

No repitas el informe del script: él ya lo tiene en el mail.

## Lo que el script no ve

Dos casos para mirar a ojo aunque no haya hallazgo:

- **Festivales y ciclos que publican la grilla en prosa.** Los cortos suelen
  estar en el cuerpo del texto, no en cards: el scraper ve una sola actividad
  y se pierden seis películas. Van a `data/manual_screenings.json`.
- **Una sala que anda bien y le falta la mitad.** El conteo no baja de golpe:
  la fuente sumó una segunda sala o una sección nueva y el scraper lee sólo la
  de siempre. Cada tanto, abrir la web de dos o tres salas y contar.

## Archivos

- `scripts/audit.py`, `scripts/audit_fuentes.py`, `scripts/audit_festivales.py`,
  `categorias.py`: el script y sus reglas.
- `data/audit.json`: el último informe en datos, con la memoria (`estado`).
- `data/audit_excepciones.json`: lo que se aceptó como está.
- `data/festivales.json`: el registro (lo que la web muestra).
- `data/festivales_radar.json`: los que vuelven todos los años.
- `data/festivales_web.json`: la huella de la web de cada festival vigente.
- `.github/workflows/audit.yml`: el informe del lunes y el centinela diario.
- `test_categorias.py`, `test_audit_agentes.py`, `test_audit_cobertura.py`,
  `test_mandar_auditoria.py`: los casos que ya pasaron, para que no vuelvan.
