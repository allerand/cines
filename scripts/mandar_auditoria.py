#!/usr/bin/env python3
"""
Manda por mail el informe de la auditoría (data/audit.html), desde el mismo
workflow que lo genera (.github/workflows/audit.yml):

    GMAIL_USER=… GMAIL_APP_PASSWORD=… python3 scripts/mandar_auditoria.py

Por qué existe: el informe se commiteaba todos los lunes y un Apps Script
aparte tenía que leerlo y mandarlo, pero ese proyecto nunca se dio de alta: no
llegó un solo mail, y el issue que abre el workflow tampoco notifica. Así el
Cineclub Farus estuvo del 29/10 al 15/11/2026 fuera de la web sin que Mateo se
enterara; se lo avisó el cineclub.

Usa la casilla de GMAIL_USER con su contraseña de aplicación: los mismos
secrets con los que el scrape lee el newsletter de Cacodelphia por IMAP, así
que no hay credenciales nuevas ni direcciones en el repo, que es público. El
mail va de esa casilla a esa misma casilla con "+cartelera", para que entre al
inbox como recibido y se pueda filtrar. AUDIT_MAIL_TO lo manda a otra dirección.

Quién audita al auditor: si data/audit.html no es de hoy, la auditoría no se
generó en esta corrida, y el asunto lo dice en vez de mandar el informe viejo
como si fuera nuevo.

Con `--alerta ARCHIVO` manda el aviso del centinela diario (audit.py
--centinela lo deja en ese archivo sólo cuando apareció un ERROR que ayer no
estaba). Si el archivo no existe o no es de hoy no manda nada y sale con 0:
la mayoría de los días no hay nada que avisar, y un mail por día sin novedades
es la forma más rápida de que dejen de leerse.

Sale con 1 si no puede mandar: el workflow queda en rojo y GitHub avisa por
mail, que es lo que tiene que pasar. Sólo stdlib.
"""
from __future__ import annotations

import argparse
import os
import re
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "data" / "audit.html"
MD = ROOT / "data" / "audit.md"
SMTP_HOST = "smtp.gmail.com"


def destinatario(user: str) -> str:
    to = os.environ.get("AUDIT_MAIL_TO", "").strip()
    if to:
        return to
    local, arroba, dominio = user.partition("@")
    return f"{local.split('+')[0]}+cartelera@{dominio}" if arroba else user


def armar_alerta(user: str, hoy: date, archivo: Path) -> EmailMessage | None:
    """El aviso del centinela, o None si no hay uno de hoy para mandar."""
    if not archivo.exists():
        return None
    html = archivo.read_text(encoding="utf-8")
    f = re.search(r"<!--\s*fecha:\s*(\d{4}-\d{2}-\d{2})\s*-->", html)
    if not f or f.group(1) != hoy.isoformat():
        return None
    m = re.search(r"<!--\s*asunto:\s*(.*?)\s*-->", html)
    msg = EmailMessage()
    msg["Subject"] = m.group(1) if m else "🔴 Algo nuevo en la cartelera"
    msg["From"] = formataddr(("Centinela cartelera", user))
    msg["To"] = destinatario(user)
    plano = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    plano = re.sub(r"</(?:p|li|h\d|tr)>", "\n", plano)
    msg.set_content(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", plano)).strip())
    msg.add_alternative(html, subtype="html")
    return msg


def armar(user: str, hoy: date) -> EmailMessage:
    html = HTML.read_text(encoding="utf-8") if HTML.exists() else ""
    texto = MD.read_text(encoding="utf-8") if MD.exists() else ""
    m = re.search(r"<!--\s*asunto:\s*(.*?)\s*-->", html)
    asunto = m.group(1) if m else "Auditoría de la cartelera"
    f = re.search(r"<!--\s*fecha:\s*(\d{4}-\d{2}-\d{2})\s*-->", html)
    if not html:
        asunto = "⚠️ La auditoría de la cartelera no se generó"
        texto = ("El workflow audit.yml corrió pero no hay data/audit.html. "
                 "Mirá la corrida en GitHub Actions.")
        html = f"<p>{texto}</p>"
    elif not f or f.group(1) != hoy.isoformat():
        viejo = f.group(1) if f else "fecha desconocida"
        aviso = (f"La auditoría de hoy no se generó: este es el último informe que "
                 f"había ({viejo}). Mirá la corrida de audit.yml en GitHub Actions.")
        asunto = f"⚠️ [informe del {viejo}] {asunto}"
        html = f'<p style="color:#d93025;font-weight:bold">{aviso}</p>\n{html}'
        texto = f"{aviso}\n\n{texto}"

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr(("Auditoría cartelera", user))
    msg["To"] = destinatario(user)
    msg.set_content(texto or re.sub(r"<[^>]+>", " ", html))
    msg.add_alternative(html, subtype="html")
    return msg


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--alerta", type=Path,
                    help="manda el aviso del centinela que está en este archivo, si es de hoy")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    user = os.environ.get("GMAIL_USER", "").strip()
    # Google muestra la contraseña de aplicación en grupos de cuatro y es
    # normal pegarla con los espacios (igual que en scraper._caco_mails).
    pwd = re.sub(r"\s+", "", os.environ.get("GMAIL_APP_PASSWORD", ""))
    if args.alerta:
        msg = armar_alerta(user, date.today(), args.alerta)
        if msg is None:
            print("Centinela: no hay aviso de hoy para mandar.")
            return 0
    if not (user and pwd):
        print("Faltan GMAIL_USER / GMAIL_APP_PASSWORD: el informe no se mandó.",
              file=sys.stderr)
        return 1
    if not args.alerta:
        msg = armar(user, date.today())
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=60) as smtp:
            smtp.login(user, pwd)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        # Sin la dirección ni la contraseña: el log de Actions es público.
        print(f"No se pudo mandar el informe: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"Informe mandado: {msg['Subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
