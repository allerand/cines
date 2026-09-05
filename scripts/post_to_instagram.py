#!/usr/bin/env python3
"""
Publica a Instagram (feed carousel + stories) usando la Meta Graph API.

Variables de entorno necesarias:
  IG_USER_ID         - Instagram Business Account ID
  IG_ACCESS_TOKEN    - User access token long-lived (60 días)
  PUBLIC_BASE_URL    - Base URL donde están servidas las PNGs públicamente
                       (ej. https://raw.githubusercontent.com/allerand/cines/main)

Uso:
    python3 scripts/post_to_instagram.py                  # hoy: feed + stories
    python3 scripts/post_to_instagram.py --feed-only      # solo carousel del feed
    python3 scripts/post_to_instagram.py --stories-only   # solo stories
    python3 scripts/post_to_instagram.py --date 2026-05-12
    python3 scripts/post_to_instagram.py --dry-run        # solo loguea

Antes de publicar le pregunta a Instagram si lo del día ya está publicado, y
si ya está no lo repite (--force saltea ese chequeo).

Códigos de salida — el workflow los usa para decidir si reintentar:
    0  quedó publicado (por esta corrida, o ya estaba de antes)
    3  NO se publicó nada y no había nada: es seguro reintentar más tarde
    1  se publicó algo y además hubo un error: NO reintentar, se duplicaría
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple, Optional

API_VERSION = "v21.0"
API_BASE = f"https://graph.facebook.com/{API_VERSION}"

# GH Actions runners a veces resuelven graph.facebook.com a IPv6 sin egress IPv6,
# resultando en "Network is unreachable". Forzamos IPv4.
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo

HERE = Path(__file__).resolve().parent.parent

# Buenos Aires es UTC-3 todo el año (no hay horario de verano), así que no hace
# falta zoneinfo ni tzdata en el runner.
BA = timezone(timedelta(hours=-3))


class Resultado(NamedTuple):
    """Qué pasó con un posteo. `ya_estaban` es Instagram diciendo que eso ya
    está publicado — no es un error, es la razón de no volver a postear."""
    publicados: int = 0
    ya_estaban: bool = False
    fallidos: int = 0

    def __add__(self, otro):
        return Resultado(self.publicados + otro.publicados,
                         self.ya_estaban or otro.ya_estaban,
                         self.fallidos + otro.fallidos)


DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _request(method: str, url: str, params: dict, retries: int = 4) -> dict:
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    if method == "GET":
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"{method} {url} → {e.code}: {err}")
        except (urllib.error.URLError, OSError) as e:
            # Network is unreachable / DNS / timeout → backoff y reintento
            last_err = e
            wait = 2 ** attempt
            print(f"  ⚠ network error ({e}); retry {attempt+1}/{retries} in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"{method} {url} → falló tras {retries} reintentos: {last_err}")


def api_post(endpoint: str, params: dict) -> dict:
    return _request("POST", f"{API_BASE}{endpoint}", params)


def api_publish(user_id: str, creation_id: str, token: str) -> dict:
    """El POST que efectivamente publica. Va SIN reintentos de red a propósito:
    si el pedido llegó a Meta y lo que se cayó fue la respuesta, reintentar
    publica dos veces el mismo container. Perder una slide se nota menos que
    duplicar el posteo, así que ante la duda no se reintenta."""
    return _request("POST", f"{API_BASE}/{user_id}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    }, retries=1)


def api_get(endpoint: str, params: dict) -> dict:
    return _request("GET", f"{API_BASE}{endpoint}", params)


def wait_container_ready(container_id: str, token: str, timeout: int = 180) -> None:
    """Los containers de IG procesan async — polleamos hasta FINISHED."""
    start = time.time()
    while time.time() - start < timeout:
        data = api_get(f"/{container_id}", {
            "fields": "status_code,status",
            "access_token": token,
        })
        status = data.get("status_code", "")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container_id} {status}: {data}")
        time.sleep(3)
    raise TimeoutError(f"Container {container_id} no llegó a FINISHED en {timeout}s")


# ---------------------------------------------------------------------------
# El último candado: preguntarle a Instagram qué hay publicado
# ---------------------------------------------------------------------------
#
# El workflow ya trae dos candados (la marca posts/<fecha>/.posteado-<modo> y
# el lock atómico en el tag ig-posted/<fecha>/<modo>), pero los dos viven en el
# repo: si alguno se pierde, o alguien corre esto a mano desde otra máquina,
# no protegen nada. Esto pregunta por el estado real de la cuenta, que es la
# única fuente de verdad sobre si el día ya se posteó.
#
# El 5/9/2026 salieron las stories dos veces: dos corridas del cron se
# solaparon y las dos vieron el directorio sin la marca, porque la marca se
# escribe recién al final. Con este chequeo, la segunda hubiera visto las
# stories de la primera y se hubiera ido sin postear.


def _fecha_ba(ts: str) -> str:
    """'2026-09-05T14:05:31+0000' → '2026-09-05' en hora de Buenos Aires."""
    dt = datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    return dt.astimezone(BA).date().isoformat()


def _publicado_el(edge: str, dia_ba: str, user_id: str, token: str,
                  media_type: Optional[str] = None) -> Optional[int]:
    """Cuántos ítems del edge (`stories` o `media`) publicó la cuenta el día
    `dia_ba`. None = no se pudo preguntar (token sin permiso, red caída): el
    que llama decide, pero NO significa cero.

    /stories devuelve sólo las stories vivas (24h), que es justo lo que hace
    falta para un posteo diario.
    """
    try:
        data = api_get(f"/{user_id}/{edge}", {
            "fields": "id,timestamp,media_type",
            "limit": "50",
            "access_token": token,
        })
    except Exception as e:
        print(f"  ⚠ no pude consultar /{edge} de la cuenta ({e})", file=sys.stderr)
        print("    sigo adelante: el lock del workflow es el que protege ahora",
              file=sys.stderr)
        return None

    encontrados = 0
    for item in data.get("data") or []:
        ts = item.get("timestamp")
        if not ts:
            continue
        try:
            if _fecha_ba(ts) != dia_ba:
                continue
        except ValueError:
            continue
        if media_type and item.get("media_type") != media_type:
            continue
        encontrados += 1
    return encontrados


HASHTAGS = (
    "#cine #cineindependiente #cinearg #buenosaires #cartelera "
    "#malba #salalugones #cacodelphia #cinelorca #cineyork "
    "#lumiton #cinecosmos #cinegaumont #cck"
)


def build_caption(date_str: str) -> str:
    y, m, d = map(int, date_str.split("-"))
    dt = date_cls(y, m, d)
    day = DAYS_ES[dt.weekday()]
    month = MONTHS_ES[m - 1]

    return (
        f"Cartelera de cine en la ciudad — {day} {d} de {month}. "
        "Toda la programación en sitedigo.com "
        "\n\n" + HASHTAGS
    )


def build_weekly_caption(week_start_str: str) -> str:
    y, m, d = map(int, week_start_str.split("-"))
    start = date_cls(y, m, d)
    end = start + __import__("datetime").timedelta(days=6)
    month_s = MONTHS_ES[start.month - 1]
    month_e = MONTHS_ES[end.month - 1]
    if start.month == end.month:
        when = f"del {start.day} al {end.day} de {month_s}"
    else:
        when = f"del {start.day} de {month_s} al {end.day} de {month_e}"

    return (
        f"Cartelera semanal de cine en la ciudad — semana {when}. "
        "Toda la programación día por día en sitedigo.com "
        "\n\n" + HASHTAGS
    )


def _slides_dir(date_str: str, fmt: str, weekly: bool = False) -> Path:
    if weekly:
        return HERE / "posts" / f"{date_str}_week" / fmt
    return HERE / "posts" / date_str / fmt


def _slide_num(p: Path) -> int:
    """Extrae el número de slide-N.png para ordenar numéricamente
    (sorted() lexicográfico pone slide-10 antes que slide-2)."""
    import re as _re
    m = _re.search(r"slide-(\d+)", p.stem)
    return int(m.group(1)) if m else 0


def collect_slides(date_str: str, fmt: str, weekly: bool = False) -> list[Path]:
    """Encuentra slides para una fecha (o semana) y formato. Compat con layout antiguo."""
    fmt_dir = _slides_dir(date_str, fmt, weekly)
    if fmt_dir.exists():
        return sorted(fmt_dir.glob("slide-*.png"), key=_slide_num)
    # Compat: PNGs viejos en posts/YYYY-MM-DD/slide-*.png
    if fmt == "portrait" and not weekly:
        legacy = HERE / "posts" / date_str
        if legacy.exists():
            return sorted(legacy.glob("slide-*.png"), key=_slide_num)
    return []


def public_url(base: str, date_str: str, fmt: str, filename: str, weekly: bool = False) -> str:
    """URL pública de una slide. Detecta si existe la versión nueva con subdir."""
    fmt_dir = _slides_dir(date_str, fmt, weekly)
    if fmt_dir.exists():
        if weekly:
            return f"{base}/posts/{date_str}_week/{fmt}/{filename}"
        return f"{base}/posts/{date_str}/{fmt}/{filename}"
    return f"{base}/posts/{date_str}/{filename}"


# ---------------------------------------------------------------------------
# Feed: carousel (1-10 slides en formato portrait 1080x1350 o square 1080x1080)
# ---------------------------------------------------------------------------

def post_feed_carousel(date_str: str, user_id: str, token: str, base: str,
                       dry_run: bool = False, weekly: bool = False,
                       force: bool = False) -> Resultado:
    slides = collect_slides(date_str, "portrait", weekly=weekly)
    if not slides:
        kind = "weekly feed" if weekly else "feed"
        print(f"  ✗ {kind}: no hay slides portrait para {date_str}",
              file=sys.stderr)
        return Resultado()
    if len(slides) > 10:
        print(f"  ! feed: IG carousel max 10 — truncando ({len(slides)} → 10)")
        slides = slides[:10]

    caption = build_weekly_caption(date_str) if weekly else build_caption(date_str)
    label = "WEEKLY FEED" if weekly else "FEED CAROUSEL"
    print(f"\n=== {label} ({len(slides)} slides) ===")
    print(f"Caption:\n{caption}\n")

    # El carrusel se compara contra HOY y no contra date_str: el semanal se
    # postea el día que se dispara, no el lunes que sale en las slides.
    if user_id and token:
        hoy_ba = datetime.now(BA).date().isoformat()
        ya = _publicado_el("media", hoy_ba, user_id, token,
                           media_type="CAROUSEL_ALBUM")
        if ya:
            print(f"  🔎 Instagram ya tiene {ya} carrusel(es) publicado(s) hoy ({hoy_ba})")
            if not force:
                print("  ⛔ no lo posteo de nuevo (con --force va igual)")
                return Resultado(ya_estaban=True)
        elif ya == 0:
            print(f"  🔎 Instagram no tiene carruseles de hoy ({hoy_ba}) — sigo")

    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'portrait', s.name, weekly=weekly)}")
        return Resultado()

    # 1) Container por slide
    children: list[str] = []
    for slide in slides:
        url = public_url(base, date_str, "portrait", slide.name, weekly=weekly)
        print(f"  → container {slide.name}")
        resp = api_post(f"/{user_id}/media", {
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": token,
        })
        children.append(resp["id"])

    # 2) Esperar processing
    for cid in children:
        wait_container_ready(cid, token)
    print(f"  ✓ {len(children)} containers listos")

    # 3) Container del carousel
    carousel = api_post(f"/{user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
        "access_token": token,
    })
    wait_container_ready(carousel["id"], token)

    # 4) Publicar
    publish = api_publish(user_id, carousel["id"], token)
    print(f"  ✅ feed posteado — id: {publish.get('id')}")
    return Resultado(publicados=1)


# ---------------------------------------------------------------------------
# Stories: una imagen por story (formato 1080x1920)
# ---------------------------------------------------------------------------

# Tope de stories por corrida — sanity bound. IG puede frenar por anti-spam
# (error 2207006) si se postea muy rápido; el delay largo entre stories (abajo)
# baja esa chance, y si igual frena, el loop corta limpio (más abajo). Subido
# de 8 a 20 porque truncaba días con más slides (a veces hay 11).
MAX_STORIES_PER_RUN = 20


def _publish_story(user_id: str, token: str, image_url: str) -> str:
    """Crea container STORIES + publica. Devuelve el id del media publicado.
    Reintenta el publish 1 vez con backoff largo si IG devuelve 2207006."""
    container = api_post(f"/{user_id}/media", {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": token,
    })
    wait_container_ready(container["id"], token)
    for attempt in range(2):
        try:
            r = api_publish(user_id, container["id"], token)
            return r.get("id", "")
        except RuntimeError as e:
            # IG código 2207006 = "media not found" típicamente significa
            # rate-limit / anti-spam. Esperar más y reintentar 1 vez.
            if "2207006" in str(e) and attempt == 0:
                print(f"    ⚠ IG dijo 2207006 — espero 90s y reintento", file=sys.stderr)
                time.sleep(90)
                continue
            raise
    return ""


def post_stories(date_str: str, user_id: str, token: str, base: str,
                 dry_run: bool = False, force: bool = False) -> Resultado:
    slides = collect_slides(date_str, "story")
    if not slides:
        print(f"  ✗ story: no hay slides en posts/{date_str}/story/",
              file=sys.stderr)
        return Resultado()

    if len(slides) > MAX_STORIES_PER_RUN:
        print(f"  ! story: cap a {MAX_STORIES_PER_RUN} de {len(slides)} (IG anti-spam)")
        slides = slides[:MAX_STORIES_PER_RUN]

    print(f"\n=== STORIES ({len(slides)} slides) ===")

    # El chequeo corre también en dry-run: es la única forma de verificar que
    # el token puede leer /stories sin postear nada de verdad.
    if user_id and token:
        ya = _publicado_el("stories", date_str, user_id, token)
        if ya:
            print(f"  🔎 Instagram ya tiene {ya} story(s) vivas de {date_str}")
            if not force:
                print("  ⛔ no las posteo de nuevo (con --force van igual)")
                return Resultado(ya_estaban=True)
        elif ya == 0:
            print(f"  🔎 Instagram no tiene stories de {date_str} — sigo")

    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'story', s.name)}")
        return Resultado()

    import random
    publicadas = 0
    fallidas = 0
    for i, slide in enumerate(slides):
        url = public_url(base, date_str, "story", slide.name)
        print(f"  → story {slide.name}")
        try:
            pub_id = _publish_story(user_id, token, url)
            publicadas += 1
            print(f"    ✓ id {pub_id}")
        except Exception as e:
            fallidas += 1
            print(f"    ✗ falló {slide.name}: {e}", file=sys.stderr)
            # Si falla por anti-spam, no tiene sentido seguir martillando
            if "2207006" in str(e):
                print(f"    ⏹  cortando — IG sigue detectando bot")
                fallidas += len(slides) - i - 1
                break
        # Delay largo con jitter entre stories para no parecer bot. Más alto
        # que antes (era 30-55s) para poder postear más sin disparar 2207006.
        if i < len(slides) - 1:
            wait_s = random.randint(45, 75)
            print(f"    ⏳ {wait_s}s hasta la próxima")
            time.sleep(wait_s)
    print(f"  ✅ {publicadas}/{len(slides)} stories posteadas"
          + (f" ({fallidas} fallaron)" if fallidas else ""))
    return Resultado(publicados=publicadas, fallidos=fallidas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _codigo_de_salida(total: Resultado, errores: list, dry_run: bool) -> int:
    """Traduce lo que pasó al contrato que espera post-ig.yml (ver docstring)."""
    if dry_run:
        return 1 if errores else 0
    if errores or total.fallidos:
        # Si YA salió algo a Instagram, reintentar duplicaría lo publicado: el
        # workflow deja el lock tomado y no vuelve a intentar solo.
        return 1 if total.publicados else 3
    if total.publicados == 0 and not total.ya_estaban:
        # No había nada que postear (típico: faltan las slides). Que el próximo
        # cron lo intente, y que el día NO quede marcado como posteado — antes
        # quedaba marcado igual, y el día se perdía sin que nadie reintentara.
        return 3
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(BA).date().isoformat())
    parser.add_argument("--week-start", default="",
                        help="YYYY-MM-DD — postea SOLO el feed semanal "
                             "(carrusel de 7 slides desde posts/<fecha>_week/portrait/)")
    parser.add_argument("--feed-only", action="store_true")
    parser.add_argument("--stories-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="No postea — solo loguea")
    parser.add_argument("--force", action="store_true",
                        help="Postea aunque Instagram ya tenga publicado lo del "
                             "día. Es el único modo de duplicar a propósito.")
    args = parser.parse_args()

    user_id = os.environ.get("IG_USER_ID", "")
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    base = os.environ.get(
        "PUBLIC_BASE_URL",
        "https://raw.githubusercontent.com/allerand/cines/main",
    ).rstrip("/")

    if not args.dry_run:
        missing = [v for v in ("IG_USER_ID", "IG_ACCESS_TOKEN", "PUBLIC_BASE_URL")
                   if not os.environ.get(v)]
        if missing:
            print(f"⚠️  faltan env vars: {', '.join(missing)}", file=sys.stderr)
            sys.exit(2)

    # Modo semanal: posteo SOLO feed carousel desde posts/<fecha>_week/portrait/
    if args.week_start:
        try:
            total = post_feed_carousel(args.week_start, user_id, token, base,
                                       dry_run=args.dry_run, weekly=True,
                                       force=args.force)
        except Exception as e:
            print(f"\n❌ error: {e}", file=sys.stderr)
            sys.exit(_codigo_de_salida(Resultado(), [e], args.dry_run))
        sys.exit(_codigo_de_salida(total, [], args.dry_run))

    do_feed = not args.stories_only
    do_stories = not args.feed_only

    # Feed y stories son independientes: si uno falla, igual intentamos el otro
    # (así un hipo puntual del carousel no nos deja sin stories, y viceversa).
    errors = []
    total = Resultado()
    if do_feed:
        try:
            total += post_feed_carousel(args.date, user_id, token, base,
                                        dry_run=args.dry_run, force=args.force)
        except Exception as e:
            print(f"\n❌ feed falló: {e}", file=sys.stderr)
            errors.append(("feed", e))
    if do_stories:
        try:
            total += post_stories(args.date, user_id, token, base,
                                  dry_run=args.dry_run, force=args.force)
        except Exception as e:
            print(f"\n❌ stories falló: {e}", file=sys.stderr)
            errors.append(("stories", e))
    sys.exit(_codigo_de_salida(total, errors, args.dry_run))


if __name__ == "__main__":
    main()
