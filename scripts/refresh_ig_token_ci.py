#!/usr/bin/env python3
"""Refresca el token long-lived de Instagram/Meta e imprime SÓLO el token nuevo
a stdout (los mensajes informativos y errores van a stderr).

Pensado para el workflow de auto-renovación: éste captura el stdout y actualiza
el secret IG_ACCESS_TOKEN con `gh secret set`. Como el token que devuelve NO es
todavía un secret registrado, el workflow lo enmascara con ::add-mask:: para que
no aparezca en los logs.

Env requeridas:
  IG_ACCESS_TOKEN  - el token long-lived ACTUAL (debe estar vigente)
  IG_APP_ID        - App ID de Facebook
  IG_APP_SECRET    - App Secret de Facebook

Meta permite intercambiar un long-lived vigente por uno nuevo (otros ~60 días)
vía grant_type=fb_exchange_token, siempre que tenga >24h de vida. Corriendo esto
cada ~15 días el token nunca llega a vencer.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://graph.facebook.com/v21.0/oauth/access_token"


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[refresh_ig_token] {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    app_id = os.environ.get("IG_APP_ID", "").strip()
    secret = os.environ.get("IG_APP_SECRET", "").strip()
    if not (token and app_id and secret):
        die("Faltan IG_ACCESS_TOKEN / IG_APP_ID / IG_APP_SECRET en el entorno.")

    query = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": secret,
        "fb_exchange_token": token,
    })
    try:
        with urllib.request.urlopen(f"{API}?{query}", timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        die(f"Error llamando a Meta: {e}")

    new_token = data.get("access_token")
    if not new_token:
        die(f"Meta no devolvió access_token. Respuesta: {data}")

    days = int(data.get("expires_in", 0)) // 86400
    print(f"[refresh_ig_token] token nuevo OK (vence en ~{days} días).",
          file=sys.stderr)
    # SÓLO el token a stdout (sin newline extra que ensucie el valor del secret):
    sys.stdout.write(new_token)


if __name__ == "__main__":
    main()
