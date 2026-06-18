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
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

API_VERSION = "v21.0"
API_BASE = f"https://graph.facebook.com/{API_VERSION}"

# GH Actions runners a veces resuelven graph.facebook.com a IPv6 sin egress IPv6,
# resultando en "Network is unreachable". Forzamos IPv4.
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo

HERE = Path(__file__).resolve().parent.parent

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
                       dry_run: bool = False, weekly: bool = False) -> None:
    slides = collect_slides(date_str, "portrait", weekly=weekly)
    if not slides:
        kind = "weekly feed" if weekly else "feed"
        print(f"  ✗ {kind}: no hay slides portrait para {date_str}",
              file=sys.stderr)
        return
    if len(slides) > 10:
        print(f"  ! feed: IG carousel max 10 — truncando ({len(slides)} → 10)")
        slides = slides[:10]

    caption = build_weekly_caption(date_str) if weekly else build_caption(date_str)
    label = "WEEKLY FEED" if weekly else "FEED CAROUSEL"
    print(f"\n=== {label} ({len(slides)} slides) ===")
    print(f"Caption:\n{caption}\n")

    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'portrait', s.name, weekly=weekly)}")
        return

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
    publish = api_post(f"/{user_id}/media_publish", {
        "creation_id": carousel["id"],
        "access_token": token,
    })
    print(f"  ✅ feed posteado — id: {publish.get('id')}")


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
            r = api_post(f"/{user_id}/media_publish", {
                "creation_id": container["id"],
                "access_token": token,
            })
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
                 dry_run: bool = False) -> None:
    slides = collect_slides(date_str, "story")
    if not slides:
        print(f"  ✗ story: no hay slides en posts/{date_str}/story/",
              file=sys.stderr)
        return

    if len(slides) > MAX_STORIES_PER_RUN:
        print(f"  ! story: cap a {MAX_STORIES_PER_RUN} de {len(slides)} (IG anti-spam)")
        slides = slides[:MAX_STORIES_PER_RUN]

    print(f"\n=== STORIES ({len(slides)} slides) ===")
    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'story', s.name)}")
        return

    import random
    for i, slide in enumerate(slides):
        url = public_url(base, date_str, "story", slide.name)
        print(f"  → story {slide.name}")
        try:
            pub_id = _publish_story(user_id, token, url)
            print(f"    ✓ id {pub_id}")
        except Exception as e:
            print(f"    ✗ falló {slide.name}: {e}", file=sys.stderr)
            # Si falla por anti-spam, no tiene sentido seguir martillando
            if "2207006" in str(e):
                print(f"    ⏹  cortando — IG sigue detectando bot")
                break
        # Delay largo con jitter entre stories para no parecer bot. Más alto
        # que antes (era 30-55s) para poder postear más sin disparar 2207006.
        if i < len(slides) - 1:
            wait_s = random.randint(45, 75)
            print(f"    ⏳ {wait_s}s hasta la próxima")
            time.sleep(wait_s)
    print(f"  ✅ {len(slides)} stories posteadas")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--week-start", default="",
                        help="YYYY-MM-DD — postea SOLO el feed semanal "
                             "(carrusel de 7 slides desde posts/<fecha>_week/portrait/)")
    parser.add_argument("--feed-only", action="store_true")
    parser.add_argument("--stories-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="No postea — solo loguea")
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
            post_feed_carousel(args.week_start, user_id, token, base,
                               dry_run=args.dry_run, weekly=True)
            return
        except Exception as e:
            print(f"\n❌ error: {e}", file=sys.stderr)
            sys.exit(1)

    do_feed = not args.stories_only
    do_stories = not args.feed_only

    try:
        if do_feed:
            post_feed_carousel(args.date, user_id, token, base, dry_run=args.dry_run)
        if do_stories:
            post_stories(args.date, user_id, token, base, dry_run=args.dry_run)
    except Exception as e:
        print(f"\n❌ error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
