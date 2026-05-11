#!/usr/bin/env python3
"""
Publica un carrusel a Instagram via Meta Graph API.

Variables de entorno necesarias:
  IG_USER_ID         - Instagram Business Account ID
  IG_ACCESS_TOKEN    - User access token long-lived
  PUBLIC_BASE_URL    - Base URL donde están servidas las PNGs públicamente
                       (ej. https://raw.githubusercontent.com/allerand/cines/main
                        o   https://sitedigo.com)

Uso:
    python3 scripts/post_to_instagram.py                # hoy
    python3 scripts/post_to_instagram.py --date 2026-05-12
    python3 scripts/post_to_instagram.py --dry-run      # solo loguea, no postea
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


def wait_container_ready(container_id: str, token: str, timeout: int = 120) -> None:
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

    # Resumen: cinco films destacados con hora
    cartelera_path = HERE / "data" / "cartelera.json"
    top_lines: list[str] = []
    if cartelera_path.exists():
        try:
            data = json.loads(cartelera_path.read_text(encoding="utf-8"))
            rows = [s for s in data.get("screenings", []) if s.get("fecha") == date_str]
            rows.sort(key=lambda s: (s.get("hora") or "99"))
            for s in rows[:6]:
                title = (s.get("title_en") or s.get("title_es") or "").strip()
                # Normalizar ALL CAPS a lowercase para consistencia con el feed
                if title and title == title.upper() and len(title) > 3:
                    title = title[0] + title[1:].lower()
                top_lines.append(f"{s.get('hora','')} · {title.lower()}")
        except Exception:
            pass

    lines = [
        f"🎬 cartelera de hoy — {day} {d} de {month}",
        "",
        "todos los horarios de las salas de cine de buenos aires",
        "malba · lugones · cacodelphia · lorca · york · munro · lumiton",
    ]
    if top_lines:
        lines.append("")
        lines.append("destacados:")
        lines.extend(top_lines)
    lines += [
        "",
        "👉 sitedigo.com — cartelera completa y links a entradas",
        "",
        "#cine #cineindependiente #cinearg #buenosaires #cartelera #malba #salalugones #cacodelphia #cinelorca #cineyork #lumiton",
    ]
    return "\n".join(lines)


def post_carousel(date_str: str, dry_run: bool = False) -> None:
    # En dry-run dejamos defaults razonables; en real, exigimos las vars.
    user_id = os.environ.get("IG_USER_ID", "")
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    base = os.environ.get(
        "PUBLIC_BASE_URL",
        "https://raw.githubusercontent.com/allerand/cines/main",
    ).rstrip("/")

    post_dir = HERE / "posts" / date_str
    slides = sorted(post_dir.glob("slide-*.png"))
    if not slides:
        print(f"  ✗ No hay slides en {post_dir}", file=sys.stderr)
        sys.exit(1)
    if len(slides) > 10:
        print(f"  ! IG carousel acepta max 10 — truncando ({len(slides)} → 10)")
        slides = slides[:10]

    caption = build_caption(date_str)
    print(f"\nCaption:\n{caption}\n")

    if dry_run:
        print("DRY RUN — no se postea")
        for slide in slides:
            print(f"  - {base}/posts/{date_str}/{slide.name}")
        return

    # Paso 1: container por slide (carousel item)
    children_ids: list[str] = []
    for slide in slides:
        image_url = f"{base}/posts/{date_str}/{slide.name}"
        print(f"  → subiendo container para {slide.name}")
        resp = api_post(f"/{user_id}/media", {
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": token,
        })
        children_ids.append(resp["id"])

    # Paso 2: esperar a que todos estén listos
    for cid in children_ids:
        wait_container_ready(cid, token)
    print(f"  ✓ {len(children_ids)} containers listos")

    # Paso 3: container del carousel
    carousel = api_post(f"/{user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": token,
    })
    carousel_id = carousel["id"]
    wait_container_ready(carousel_id, token)

    # Paso 4: publicar
    publish = api_post(f"/{user_id}/media_publish", {
        "creation_id": carousel_id,
        "access_token": token,
    })
    print(f"\n✅ posteado — IG media id: {publish.get('id')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--dry-run", action="store_true",
                        help="No postea — solo loguea lo que haría")
    args = parser.parse_args()

    # Validación temprana de env vars
    missing = [v for v in ("IG_USER_ID", "IG_ACCESS_TOKEN", "PUBLIC_BASE_URL")
               if not os.environ.get(v)]
    if missing and not args.dry_run:
        print(f"⚠️  Faltan vars: {', '.join(missing)}", file=sys.stderr)
        print("Seteá los GitHub Secrets o exportá las vars antes de correr.", file=sys.stderr)
        sys.exit(2)

    post_carousel(args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
