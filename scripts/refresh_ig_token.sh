#!/usr/bin/env bash
#
# Convierte un token corto de Instagram/Meta en uno long-lived (60 días),
# lo valida y te dice exactamente qué pegar en el secret IG_ACCESS_TOKEN.
#
# Cuándo usarlo:
#   - Si el token YA venció: primero generá uno NUEVO en Meta for Developers →
#     tu app → producto "Instagram" → "Generate access token" (elegí
#     @sitedigocine). Copiá el token corto (empieza con EAA...) y usalo acá.
#   - Si el token TODAVÍA es válido (renovación preventiva): podés pasar el
#     long-lived actual como SHORT_TOKEN; Meta te devuelve uno nuevo con otros
#     60 días.
#
# Uso:
#   APP_ID=... APP_SECRET=... SHORT_TOKEN=EAA... bash scripts/refresh_ig_token.sh
#
# APP_ID / APP_SECRET salen de Meta for Developers → tu app → App settings → Basic.

set -euo pipefail

API_VERSION="v21.0"

: "${APP_ID:?Falta APP_ID (Meta → App settings → Basic → App ID)}"
: "${APP_SECRET:?Falta APP_SECRET (Meta → App settings → Basic → App Secret)}"
: "${SHORT_TOKEN:?Falta SHORT_TOKEN (el token EAA... recién generado en Meta)}"

echo "→ Intercambiando por token long-lived…"
RESP="$(curl -sS "https://graph.facebook.com/${API_VERSION}/oauth/access_token?grant_type=fb_exchange_token&client_id=${APP_ID}&client_secret=${APP_SECRET}&fb_exchange_token=${SHORT_TOKEN}")"

# Extraer access_token y expires_in sin depender de jq
LONG_TOKEN="$(printf '%s' "$RESP" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
EXPIRES="$(printf '%s' "$RESP" | sed -n 's/.*"expires_in":\([0-9]*\).*/\1/p')"

if [ -z "$LONG_TOKEN" ]; then
  echo "✗ No se pudo obtener el token. Respuesta de Meta:"
  echo "$RESP"
  echo
  echo "Causas comunes: SHORT_TOKEN vencido/incorrecto, o APP_ID/APP_SECRET mal."
  exit 1
fi

DAYS=$(( ${EXPIRES:-0} / 86400 ))
echo "✓ Token long-lived obtenido (vence en ~${DAYS} días)."
echo

echo "→ Validando el token (debug_token)…"
curl -sS "https://graph.facebook.com/debug_token?input_token=${LONG_TOKEN}&access_token=${APP_ID}|${APP_SECRET}" \
  | sed -n 's/.*"expires_at":\([0-9]*\).*/  expira (epoch): \1/p' || true
echo

echo "──────────────────────────────────────────────────────────────"
echo "PEGÁ ESTE VALOR en el secret IG_ACCESS_TOKEN de GitHub:"
echo "  https://github.com/allerand/cines/settings/secrets/actions"
echo "──────────────────────────────────────────────────────────────"
echo "$LONG_TOKEN"
echo "──────────────────────────────────────────────────────────────"
echo
echo "Si tenés la CLI 'gh' logueada, podés setearlo directo con:"
echo "  gh secret set IG_ACCESS_TOKEN --repo allerand/cines --body '<el token de arriba>'"
