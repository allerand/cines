---
name: auditoria
description: Auditoría semanal de la cartelera de sitedigo.com — revisa qué cines están caídos, qué funciones faltan y qué datos salieron sucios, y arregla lo que se pueda. Usar cuando el usuario pida revisar/auditar los cines, chequear si falta programación, o invoque /auditoria.
---

# Auditoría de la cartelera

Objetivo: que mantener la web cueste poco. Cada scraper de `scraper.py` atrapa
sus excepciones y devuelve `[]`, así que **cuando una fuente cambia de HTML el
cine desaparece de la web sin que nada falle**. Esta rutina es lo que convierte
ese silencio en una lista de cosas para arreglar.

## 1. Correr el chequeo mecánico

```bash
python3 scripts/audit.py
```

Sale con código 1 si hay ERRORes. Chequea tres cosas:

- **Frescura** — hace cuánto no se actualiza `data/cartelera.json` (el scrape
  diario corre 07:15 UTC; más de 36 h es una corrida perdida).
- **Cobertura** — funciones por cine contra su propio histórico (sale de los
  commits de `data/cartelera.json`) y contra sondas HTTP a cada fuente.
- **Calidad** — director duplicado, título que en realidad es el copete del
  ciclo, horas inválidas, años imposibles, dos títulos en el mismo horario.

Con `--offline` saltea las sondas (rápido). El histórico necesita historia de
git: en CI hace falta `fetch-depth: 0`.

## 2. Verificar a mano lo que el script no puede

El script dice "este cine está raro"; confirmar contra la fuente es trabajo de
lectura. Para cada ERROR de cobertura:

1. Abrir la página del cine y contar qué hay publicado de verdad.
2. Comparar con `data/cartelera.json`.
3. Si la fuente tiene programación y nosotros no: leer el scraper de ese cine y
   encontrar qué cambió del HTML.

Dos casos que el script **no** detecta y conviene mirar a ojo cada semana:

- **Festivales y ciclos que publican la grilla en prosa.** Los cortos suelen
  estar en el cuerpo del texto, no en cards: el scraper ve una sola actividad
  y se pierden 6 películas. Van a `data/manual_screenings.json`.
- **Programas dobles escritos como un título único** ("PELI A de X (1995, 55
  min.) y PELI B de Y"). Se reemplazan por dos funciones en
  `manual_screenings.json` + una regla en `descartar`.

## 3. Arreglar

Por orden de preferencia:

1. **Arreglar el scraper** si la fuente cambió de estructura. Es lo único que
   escala. Testear el parser contra el texto real de la página (guardar el HTML
   en el scratchpad y correr sólo la función de parseo: `scraper.py` necesita
   Python 3.10+, y si el Python local es más viejo se puede extraer la función
   con `ast` y ejecutarla suelta).
2. **`data/manual_screenings.json`** para lo que ningún scraper puede sacar
   (festivales en prosa, programas dobles). Se filtra solo a
   `[hoy, hoy+semanas]`: las funciones viejas no hay que borrarlas.
3. **`data/metadata_overrides.json`** para director/año/país/Letterboxd mal
   matcheados. Verificar cada slug de Letterboxd antes de agregarlo: que
   devuelva 200 y que coincida el director.

Reglas de la casa: comentar el **por qué** del fix, no el qué; y arreglar el
dato publicado en `data/cartelera.json` además del scraper, para que la web no
espere al próximo scrape.

## 4. Cerrar

Commitear con un mensaje que diga qué se rompió y por qué, y reportar al
usuario: qué se arregló, qué quedó pendiente y qué necesita decisión suya.
