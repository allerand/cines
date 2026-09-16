"""
El director impreso en el poster, leído con Claude.

Cacodelphia no publica director ni año en ningún lado —la API de la ficha trae
"datosTecnicos": "." en todas las películas—, pero el poster casi siempre trae
el crédito: "Una película de Avelina Prat", "dirigida por Leandro Cerro", "un
film de Leonardo Favio". Sin director ni año el enrichment elige por título y
duración, y el 16/9/2026 Nazareno Cruz y el lobo quedó sin ficha: Letterboxd le
da 85 minutos y el cine 92, así que la única película que se llama así quedó
descartada por duración. Con el director el enrichment va por el camino
validado: la ficha tiene que ser de ese director, o la función queda vacía.

Lo que se pide es una TRANSCRIPCIÓN, no una identificación. Si el modelo
reconociera la película por lo que sabe, un error suyo pasaría a ser un dato de
la fuente (run.py publica el director de la función aunque Letterboxd no la
encuentre). Por eso tiene que devolver también el fragmento del poster donde
leyó el nombre, y acá se revisa que el nombre esté adentro y que el fragmento
sea un crédito de dirección: "Retrospectiva Leonardo Favio" o "basada en el
best seller de Max Porter" no lo son.

Sin ANTHROPIC_API_KEY no se lee nada y todo sigue como antes. Cada poster se lee
una sola vez: el resultado queda en data/posters.json por URL (Cacodelphia sube
cada poster con un nombre único, así que un poster nuevo es una URL nueva).
"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

POSTERS_JSON = Path(__file__).parent / "data" / "posters.json"

MODELO = "claude-opus-5"

# El límite de la API es 5 MB por imagen; los posters de Cacodelphia pesan
# ~60 KB. Algo mucho más grande no es un poster.
_MAX_BYTES = 5 * 1024 * 1024

_MEDIA_TYPES = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg",
                "jpeg": "image/jpeg", "gif": "image/gif"}

_PROMPT = """\
Este es el poster de «{titulo}», tal como lo publica un cine de Buenos Aires.

Transcribí el crédito de dirección que esté IMPRESO en el poster: "Una película \
de …", "Un film de …", "Dirigida por …", "Escrita y dirigida por …", "Del \
director …", "A film by …", "Directed by …".

- credito: el fragmento tal cual se lee en la imagen, con el nombre incluido \
(por ejemplo "un film de Leonardo Favio").
- director: sólo el nombre, escrito como en el poster. Si son varios, separados \
por coma.

Dejá los dos vacíos si el poster no trae ese crédito o no se llega a leer. No \
completes con lo que sepas de la película: vale sólo lo que está escrito. Tampoco \
valen otros créditos (guion, producción, "basada en la novela de…", coordinación, \
curaduría) ni el nombre de una retrospectiva o de un ciclo: "Retrospectiva \
Leonardo Favio" no es un crédito de dirección."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "director": {"type": "string"},
        "credito": {"type": "string"},
    },
    "required": ["director", "credito"],
    "additionalProperties": False,
}

# Palabras que hacen de un fragmento un crédito de dirección. "de" sola no
# alcanza: "basada en el best seller de Max Porter" también la tiene.
_CUE_RE = re.compile(
    r"\b(pelicula|film|dirigid[ao]s?|direccion|director[a]?|directed|realizad[ao]|realizacion|by)\b"
)

_avisado_sin_clave = False


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def director_valido(director: str, credito: str) -> str:
    """El director, si el fragmento lo respalda; si no, "".

    Tres condiciones: que parezca un nombre (sin dígitos, corto), que cada
    palabra del nombre esté en el fragmento, y que el fragmento sea un crédito
    de dirección y no cualquier mención.
    """
    director = re.sub(r"\s+", " ", director or "").strip(" .,;:-")
    if not director or len(director) > 80 or re.search(r"\d", director):
        return ""
    palabras = _norm(director).split()
    if not palabras or len(palabras) > 12:
        return ""
    en_credito = f" {_norm(credito)} "
    if not all(f" {p} " in en_credito for p in palabras):
        return ""
    if not _CUE_RE.search(en_credito):
        return ""
    return director


def _cargar() -> dict:
    try:
        return json.loads(POSTERS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(cache: dict) -> None:
    POSTERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    POSTERS_JSON.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bajar(url: str) -> Optional[tuple[bytes, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            datos = r.read(_MAX_BYTES + 1)
            tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    except Exception:
        return None
    if not datos or len(datos) > _MAX_BYTES:
        return None
    if tipo not in _MEDIA_TYPES.values():
        tipo = _MEDIA_TYPES.get(url.rsplit(".", 1)[-1].lower().split("?")[0], "")
    return (datos, tipo) if tipo else None


def _leer(imagen: bytes, media_type: str, titulo: str) -> Optional[dict]:
    """Una llamada a Claude. None si no hubo respuesta que valga guardar
    (error de red o de la API): el poster se reintenta en la próxima corrida."""
    import anthropic  # sólo hace falta con clave; así `import scraper` no la pide

    client = anthropic.Anthropic()
    try:
        # fallbacks="default": si el clasificador de seguridad rechaza el pedido
        # (improbable con un poster, pero pasa), la API lo reintenta sola con el
        # modelo que corresponda en vez de devolver el rechazo.
        resp = client.beta.messages.create(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            # Transcribir un crédito no pide pensar mucho.
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type,
                        "data": base64.standard_b64encode(imagen).decode("ascii"),
                    }},
                    {"type": "text", "text": _PROMPT.format(titulo=titulo)},
                ],
            }],
        )
    except anthropic.APIConnectionError as e:
        print(f"(poster de {titulo!r}: sin conexión con la API — {e})", end=" ", flush=True)
        return None
    except anthropic.APIStatusError as e:
        print(f"(poster de {titulo!r}: la API contestó {e.status_code})", end=" ", flush=True)
        return None

    if resp.stop_reason == "refusal":
        # Rechazado también por el fallback: mañana va a pasar lo mismo.
        return {"director": "", "credito": "", "rechazo": True}
    if resp.stop_reason != "end_turn":
        return None
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        datos = json.loads(texto)
    except ValueError:
        return None
    return {"director": str(datos.get("director") or ""),
            "credito": str(datos.get("credito") or "")}


def director_del_poster(url: str, titulo: str) -> str:
    """Director impreso en el poster de `url`, o "" si no hay crédito legible.

    La respuesta cruda del modelo queda en el caché y el control de
    director_valido se aplica al leerla: si la regla se endurece, vale también
    para los posters ya leídos.
    """
    global _avisado_sin_clave
    if not url:
        return ""
    cache = _cargar()
    if url in cache:
        e = cache[url]
        return director_valido(e.get("director", ""), e.get("credito", ""))

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        if not _avisado_sin_clave:
            print("(sin ANTHROPIC_API_KEY: no se leen los posters)", end=" ", flush=True)
            _avisado_sin_clave = True
        return ""

    bajado = _bajar(url)
    if not bajado:
        return ""
    leido = _leer(bajado[0], bajado[1], titulo)
    if leido is None:
        return ""
    leido.update(titulo=titulo, fecha=date.today().isoformat())
    cache[url] = leido
    _guardar(cache)
    return director_valido(leido["director"], leido["credito"])
