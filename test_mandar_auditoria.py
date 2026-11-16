#!/usr/bin/env python3
"""
Test local de scripts/mandar_auditoria.py, sin red ni mails de verdad:

    python3 test_mandar_auditoria.py

El informe de la auditoría se generaba todos los lunes y no le llegaba a nadie:
el Apps Script que lo tenía que mandar nunca se dio de alta. Estos casos cubren
que el mail salga, a quién, con qué asunto, y que un informe viejo o ausente
no pase por uno de hoy.
"""
import os
import smtplib
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import mandar_auditoria as ma                       # noqa: E402

HOY = date.today()
INFORME = (f"<!-- asunto: 🔴 Hay 2 cosas para mirar en 2 cines — cartelera al {HOY:%d/%m} -->\n"
           f"<!-- fecha: {HOY.isoformat()} -->\n<div><h2>Auditoría de la cartelera</h2>"
           "<li><strong>Cineclub Farus</strong> — lleva 12 días sin ninguna función</li></div>\n")
MD = "# Auditoría de la cartelera\n\n- **Cineclub Farus** — lleva 12 días sin ninguna función\n"

enviados: list = []
logins: list = []
falla_login = False


class SMTPFalso:
    def __init__(self, host, port, timeout=None):
        assert (host, port) == ("smtp.gmail.com", 465), (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pwd):
        if falla_login:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        logins.append((user, pwd))

    def send_message(self, msg):
        enviados.append(msg)


ma.smtplib.SMTP_SSL = SMTPFalso
tmp = Path(tempfile.mkdtemp())
ma.HTML, ma.MD = tmp / "audit.html", tmp / "audit.md"


def correr(html=INFORME, md=MD, user="alguien@gmail.com", pwd="abcd efgh ijkl mnop", to=""):
    enviados.clear()
    logins.clear()
    for p, contenido in ((ma.HTML, html), (ma.MD, md)):
        if contenido is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(contenido, encoding="utf-8")
    os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"] = user, pwd
    os.environ["AUDIT_MAIL_TO"] = to
    return ma.main()


# 1. El informe de hoy sale, de la casilla a la misma casilla con +cartelera.
assert correr() == 0
assert logins == [("alguien@gmail.com", "abcdefghijklmnop")], logins
(msg,) = enviados
assert msg["To"] == "alguien+cartelera@gmail.com", msg["To"]
assert msg["From"] == "Auditoría cartelera <alguien@gmail.com>", msg["From"]
assert msg["Subject"] == f"🔴 Hay 2 cosas para mirar en 2 cines — cartelera al {HOY:%d/%m}", msg["Subject"]
html = msg.get_body(("html",)).get_content()
assert "Cineclub Farus" in html and "no se generó" not in html
assert "lleva 12 días" in msg.get_body(("plain",)).get_content()
print("✓ el informe de hoy sale con su asunto, a la misma casilla con +cartelera")

# 2. Con una etiqueta ya puesta en el usuario no se encadenan dos.
assert correr(user="alguien+bot@gmail.com") == 0
assert enviados[0]["To"] == "alguien+cartelera@gmail.com", enviados[0]["To"]
# Y AUDIT_MAIL_TO manda a otra dirección.
assert correr(to="otra@ejemplo.com") == 0
assert enviados[0]["To"] == "otra@ejemplo.com"
print("✓ destinatario: sin doble etiqueta, y AUDIT_MAIL_TO lo cambia")

# 3. Un informe viejo no pasa por uno de hoy.
viejo = INFORME.replace(HOY.isoformat(), "2026-11-09")
assert correr(html=viejo) == 0
(msg,) = enviados
assert msg["Subject"].startswith("⚠️ [informe del 2026-11-09]"), msg["Subject"]
assert "no se generó" in msg.get_body(("html",)).get_content()
print("✓ si la auditoría de hoy no se generó, el asunto lo dice")

# 4. Sin informe, igual sale un mail que lo dice.
assert correr(html=None, md=None) == 0
assert enviados[0]["Subject"] == "⚠️ La auditoría de la cartelera no se generó"
print("✓ sin informe, sale un aviso en vez de nada")

# 5. Sin credenciales o con la contraseña rechazada: exit 1 (workflow en rojo).
assert correr(pwd="") == 1 and not enviados and not logins
falla_login = True
assert correr() == 1 and not enviados
falla_login = False
print("✓ sin credenciales o rechazadas, falla en voz alta y no manda nada")

# 6. El aviso del centinela: sale sólo si hay un archivo, y sólo si es de hoy.
alerta = tmp / "alerta.html"
ALERTA = (f"<!-- asunto: 🔴 Nuevo en la cartelera: Sala Lugones -->\n<!-- fecha: {HOY.isoformat()} -->\n"
          "<div><h2>Centinela de la cartelera</h2><ul><li><strong>Sala Lugones</strong> (categorías): "
          "hay funciones que dicen el nombre de un ciclo en vez de la película</li></ul></div>\n")


def centinela(contenido):
    enviados.clear()
    alerta.unlink(missing_ok=True)
    if contenido is not None:
        alerta.write_text(contenido, encoding="utf-8")
    os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"] = "alguien@gmail.com", "abcd"
    os.environ["AUDIT_MAIL_TO"] = ""
    return ma.main(["--alerta", str(alerta)])


assert centinela(None) == 0 and not enviados
assert centinela(ALERTA.replace(HOY.isoformat(), "2026-11-09")) == 0 and not enviados
assert centinela(ALERTA) == 0
(msg,) = enviados
assert msg["Subject"] == "🔴 Nuevo en la cartelera: Sala Lugones", msg["Subject"]
assert msg["To"] == "alguien+cartelera@gmail.com", msg["To"]
assert msg["From"] == "Centinela cartelera <alguien@gmail.com>", msg["From"]
plano = msg.get_body(("plain",)).get_content()
assert "Sala Lugones" in plano and "<" not in plano and "asunto:" not in plano, plano
assert "nombre de un ciclo" in msg.get_body(("html",)).get_content()
print("✓ el centinela manda su aviso sólo cuando hay uno de hoy, y si no, no manda nada")

print("\nTodo OK")
