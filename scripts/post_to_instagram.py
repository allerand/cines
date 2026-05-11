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
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_cls
from pathlib import Path

API_VERSION = "v21.0"
API_BASE = f"https://graph.facebook.com/{API_VERSION}"

HERE = Path(__file__).resolve().parent.parent

DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _request(method: str, url: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    if method == "GET":
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} → {e.code}: {err}")


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


def build_caption(date_str: str) -> str:
    y, m, d = map(int, date_str.split("-"))
    dt = date_cls(y, m, d)
    day = DAYS_ES[dt.weekday()]
    month = MONTHS_ES[m - 1]

    cartelera_path = HERE / "data" / "cartelera.json"
    top_lines: list[str] = []
    if cartelera_path.exists():
        try:
            data = json.loads(cartelera_path.read_text(encoding="utf-8"))
            rows = [s for s in data.get("screenings", []) if s.get("fecha") == date_str]
            rows.sort(key=lambda s: (s.get("hora") or "99"))
            for s in rows[:6]:
                title = (s.get("title_en") or s.get("title_es") or "").strip()
                if title and title == title.upper() and len(title) > 3:
                    title = title[0] + title[1:].lower()
                top_lines.append(f"{s.get('hora','')} · {title.lower()}")
        except Exception:
            pass

    lines = [
        f"🎬 la cartelera de hoy — {day} {d} de {month}",
        "",
        "todos los horarios de las salas de cine de buenos aires",
        "malba · lugones · cacodelphia · lorca · york · munro · lumiton · cosmos · gaumont · cck",
    ]
    if top_lines:
        lines.append("")
        lines.append("destacados:")
        lines.extend(top_lines)
    lines += [
        "",
        "👉 toda la cartelera de la semana en sitedigo.com",
        "(link también en bio)",
        "",
        "#cine #cineindependiente #cinearg #buenosaires #cartelera "
        "#malba #salalugones #cacodelphia #cinelorca #cineyork #lumiton "
        "#cinecosmos #cinegaumont #cck",
    ]
    return "\n".join(lines)


def collect_slides(date_str: str, fmt: str) -> list[Path]:
    """Encuentra slides para una fecha y formato. Compat con layout antiguo."""
    fmt_dir = HERE / "posts" / date_str / fmt
    if fmt_dir.exists():
        return sorted(fmt_dir.glob("slide-*.png"))
    # Compat: PNGs viejos en posts/YYYY-MM-DD/slide-*.png
    if fmt == "portrait":
        legacy = HERE / "posts" / date_str
        if legacy.exists():
            return sorted(legacy.glob("slide-*.png"))
    return []


def public_url(base: str, date_str: str, fmt: str, filename: str) -> str:
    """URL pública de una slide. Detecta si existe la versión nueva con subdir."""
    fmt_dir = HERE / "posts" / date_str / fmt
    if fmt_dir.exists():
        return f"{base}/posts/{date_str}/{fmt}/{filename}"
    return f"{base}/posts/{date_str}/{filename}"


# ---------------------------------------------------------------------------
# Feed: carousel (1-10 slides en formato portrait 1080x1350 o square 1080x1080)
# ---------------------------------------------------------------------------

def post_feed_carousel(date_str: str, user_id: str, token: str, base: str,
                       dry_run: bool = False) -> None:
    slides = collect_slides(date_str, "portrait")
    if not slides:
        print(f"  ✗ feed: no hay slides portrait en posts/{date_str}/portrait/",
              file=sys.stderr)
        return
    if len(slides) > 10:
        print(f"  ! feed: IG carousel max 10 — truncando ({len(slides)} → 10)")
        slides = slides[:10]

    caption = build_caption(date_str)
    print(f"\n=== FEED CAROUSEL ({len(slides)} slides) ===")
    print(f"Caption:\n{caption}\n")

    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'portrait', s.name)}")
        return

    # 1) Container por slide
    children: list[str] = []
    for slide in slides:
        url = public_url(base, date_str, "portrait", slide.name)
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

def post_stories(date_str: str, user_id: str, token: str, base: str,
                 dry_run: bool = False) -> None:
    slides = collect_slides(date_str, "story")
    if not slides:
        print(f"  ✗ story: no hay slides en posts/{date_str}/story/",
              file=sys.stderr)
        return

    print(f"\n=== STORIES ({len(slides)} slides) ===")
    if dry_run:
        for s in slides:
            print(f"  - {public_url(base, date_str, 'story', s.name)}")
        return

    for slide in slides:
        url = public_url(base, date_str, "story", slide.name)
        print(f"  → story {slide.name}")
        # 1) Container tipo STORIES
        container = api_post(f"/{user_id}/media", {
            "image_url": url,
            "media_type": "STORIES",
            "access_token": token,
        })
        wait_container_ready(container["id"], token)
        # 2) Publicar
        publish = api_post(f"/{user_id}/media_publish", {
            "creation_id": container["id"],
            "access_token": token,
        })
        print(f"    ✓ id {publish.get('id')}")
        # Esperar 4s entre stories para no chocar contra rate limits
        time.sleep(4)
    print(f"  ✅ {len(slides)} stories posteadas")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date_cls.today().isoformat())
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
