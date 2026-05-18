#!/usr/bin/env python3
"""
Manda el newsletter semanal vía Buttondown.

Lee data/cartelera.json y arma el HTML día por día (lun → dom) a partir de
una fecha de comienzo (por defecto: próximo lunes desde hoy en BA).

Variables de entorno necesarias:
  BUTTONDOWN_API_KEY    - token v1 de buttondown.com/settings/api-keys

Uso:
    python3 scripts/send_newsletter.py                # publica el broadcast
    python3 scripts/send_newsletter.py --dry-run      # imprime el HTML
    python3 scripts/send_newsletter.py --week 2026-05-25
"""
import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CARTELERA = HERE / "data" / "cartelera.json"

# Forzar IPv4 (mismo patch que post_to_instagram para runners de GH Actions)
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4

DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def next_monday(today: date) -> date:
    """Si hoy es lunes, devuelve hoy. Sino el próximo lunes."""
    offset = (7 - today.weekday()) % 7 or 0
    # weekday: Mon=0; queremos offset=0 si lunes, sino días al próximo lunes
    if today.weekday() == 0:
        return today
    offset = (7 - today.weekday()) % 7
    return today + timedelta(days=offset)


def caption_dates(start: date, end: date) -> str:
    mS = MONTHS_ES[start.month - 1]
    mE = MONTHS_ES[end.month - 1]
    if start.month == end.month:
        return f"del {start.day} al {end.day} de {mS}"
    return f"del {start.day} de {mS} al {end.day} de {mE}"


def build_html(week_start: date) -> tuple[str, str]:
    """Devuelve (subject, html_body)."""
    week_end = week_start + timedelta(days=6)
    data = json.loads(CARTELERA.read_text(encoding="utf-8"))
    screenings = data.get("screenings", [])

    # Filtrar a la semana
    week_set = {(week_start + timedelta(days=i)).isoformat() for i in range(7)}
    week = [s for s in screenings if s.get("fecha") in week_set]
    # Agrupar por fecha → lista ordenada por hora
    by_day: dict[str, list[dict]] = {}
    for s in week:
        by_day.setdefault(s["fecha"], []).append(s)
    for day, films in by_day.items():
        films.sort(key=lambda x: (x.get("hora") or "99", x.get("cine") or ""))

    when = caption_dates(week_start, week_end)
    subject = f"Cartelera de cine — semana {when}"

    # HTML
    parts: list[str] = [
        '<div style="font-family: -apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;'
        ' max-width:640px;margin:0 auto;color:#1a1a1a;line-height:1.5;">',
        f'<h1 style="font-size:20px;font-weight:700;margin:0 0 6px;">Cartelera de cine</h1>',
        f'<p style="margin:0 0 24px;color:#666;font-size:14px;">'
        f'Programación de las salas de cine de la ciudad, semana {when}.</p>',
    ]

    for i in range(7):
        d = week_start + timedelta(days=i)
        day_name = DAYS_ES[d.weekday()]
        films = by_day.get(d.isoformat(), [])
        parts.append(
            f'<h2 style="font-size:14px;font-weight:700;letter-spacing:0.06em;'
            f'text-transform:uppercase;margin:24px 0 8px;color:#1a1a1a;'
            f'border-bottom:1px solid #e0e0e0;padding-bottom:4px;">'
            f'{escape(day_name)} {d.day} de {MONTHS_ES[d.month - 1]}'
            f'  <span style="float:right;font-weight:400;color:#999;">{len(films)} func.</span>'
            f'</h2>'
        )
        if not films:
            parts.append('<p style="margin:6px 0;color:#999;font-size:14px;">— sin funciones —</p>')
            continue
        # Lista compacta
        parts.append('<ul style="list-style:none;padding:0;margin:0;font-size:14px;">')
        for s in films:
            hora = escape(s.get("hora") or "??")
            title = escape(s.get("title_es") or s.get("title_en") or "(sin título)")
            cine = escape(s.get("cine") or "")
            director = (s.get("director") or "").strip()
            year = s.get("year")
            duration = s.get("duration")
            lb = s.get("letterboxd") or ""
            meta_extras = []
            if director:
                meta_extras.append(escape(director))
            if year:
                meta_extras.append(str(year))
            if duration:
                meta_extras.append(f"{duration} min")
            meta_str = " · ".join(meta_extras)
            title_html = (
                f'<a href="{escape(lb)}" style="color:#1a1a1a;text-decoration:none;border-bottom:1px solid #999;">{title}</a>'
                if lb else title
            )
            parts.append(
                '<li style="padding:6px 0;border-bottom:1px solid #f0f0f0;">'
                f'<strong style="display:inline-block;width:54px;color:#333;">{hora}</strong>'
                f' <span style="font-size:11px;color:#777;text-transform:uppercase;letter-spacing:0.04em;'
                f'border:1px solid #ddd;padding:1px 6px;border-radius:3px;margin-right:6px;">{cine}</span>'
                f' {title_html}'
                + (f'<div style="margin-left:54px;color:#777;font-size:13px;">{escape(meta_str)}</div>' if meta_str else '')
                + '</li>'
            )
        parts.append('</ul>')

    parts.append(
        '<hr style="border:none;border-top:1px solid #e0e0e0;margin:32px 0 12px;">'
        '<p style="margin:0;font-size:12px;color:#999;">'
        'Todas las funciones también en '
        '<a href="https://sitedigo.com" style="color:#1a1a1a;">sitedigo.com</a> · '
        '<a href="https://instagram.com/sitedigocine" style="color:#1a1a1a;">@sitedigocine</a> en Instagram.'
        '</p>'
        '</div>'
    )
    return subject, "".join(parts)


def buttondown_create_email(subject: str, body: str, api_key: str) -> dict:
    """Crea un email en Buttondown y lo envía a todos los suscriptores."""
    url = "https://api.buttondown.email/v1/emails"
    payload = json.dumps({
        "subject": subject,
        "body": body,
        "status": "about_to_send",  # dispara el envío inmediato a todos los suscriptores
        "email_type": "public",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
            # Buttondown exige este header para confirmar que sabemos que
            # 'about_to_send' dispara el envío real e inmediato a todos los
            # suscriptores. Se pide una sola vez por API key.
            "X-Buttondown-Live-Dangerously": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", default="",
                        help="YYYY-MM-DD del lunes de la semana (default: próximo lunes)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Imprime el HTML, no manda nada")
    args = parser.parse_args()

    if args.week:
        try:
            week_start = date.fromisoformat(args.week)
        except ValueError:
            print(f"❌ --week debe ser YYYY-MM-DD, recibí {args.week!r}", file=sys.stderr)
            sys.exit(2)
    else:
        week_start = next_monday(date.today())

    subject, body = build_html(week_start)
    print(f"📬 subject: {subject}")
    print(f"📅 semana:  {week_start} → {week_start + timedelta(days=6)}")
    print(f"📝 body len: {len(body)} bytes\n")

    if args.dry_run:
        print(body)
        return

    api_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not api_key:
        print("❌ falta BUTTONDOWN_API_KEY", file=sys.stderr)
        sys.exit(2)

    try:
        resp = buttondown_create_email(subject, body, api_key)
        print(f"✅ enviado — id: {resp.get('id')}, status: {resp.get('status')}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        print(f"❌ {e.code} — {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
