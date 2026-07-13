# Setup del auto-posteo a Instagram

Esta guía configura el posteo automático de la cartelera diaria a `@sitedigocine`
usando la Meta Graph API. Una vez configurado, el workflow de GitHub Actions
postea solo todos los días a las 10am Buenos Aires.

## Resumen del flujo

```
10:00 BA → GH Actions corre el cron
          ├─ scrapea los cines + Letterboxd/IMDB
          ├─ genera posts/YYYY-MM-DD/slide-N.png (uno por slide del carrusel)
          ├─ commitea al repo (raw.githubusercontent.com sirve las PNGs)
          └─ llama a Meta Graph API → carrusel a @sitedigocine
```

## Paso 1: Convertir Instagram a cuenta Business

1. Desde la app de Instagram (con @sitedigocine logueada): **Configuración → Cuenta → Cambiar a cuenta profesional**
2. Elegí categoría (ej. "Sitio web de medios y noticias" o "Producto/servicio")
3. Elegí **Empresa** (Business)
4. Saltá los pasos opcionales hasta llegar al panel profesional

## Paso 2: Vincular a una Facebook Page

La Graph API requiere que IG esté vinculada a una FB Page del mismo dueño.

1. Desde **facebook.com → Tu perfil → Páginas → Crear nueva página**
2. Nombre: "Sitedigo Cine" (o lo que prefieras)
3. Categoría: "Sitio web de medios y noticias"
4. Una vez creada, andá a **Configuración de la página → Cuentas vinculadas → Instagram → Conectar cuenta** y logueate con @sitedigocine

## Paso 3: Crear una app en Meta for Developers

1. Andá a https://developers.facebook.com/ → **My Apps** → **Create App**
2. **Use case**: "Other"
3. **App type**: "Business"
4. Nombre: "sitedigocine-poster"
5. Email de contacto: el tuyo
6. **Create app**

## Paso 4: Agregar el producto "Instagram"

1. En tu app → **Add product** (sidebar izquierdo)
2. Buscá **Instagram** → **Set up**
3. En la próxima pantalla, **Generate access token** → seleccioná @sitedigocine
4. Aceptá los permisos solicitados (van a incluir `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `business_management`)
5. **Copiá el token que aparece** — empieza con `EAA...`. **Cuidado: solo se muestra una vez.**

## Paso 5: Convertir el token corto en long-lived (60 días)

Por default el token dura solo 1 hora. Lo cambiamos por uno de 60 días.

En tu terminal, reemplazá `APP_ID`, `APP_SECRET` (de Meta for Developers → tu app → **App settings → Basic**) y el token corto:

```bash
SHORT_TOKEN="EAA...el token corto..."
APP_ID="..."
APP_SECRET="..."

curl -s "https://graph.facebook.com/v21.0/oauth/access_token?\
grant_type=fb_exchange_token&\
client_id=$APP_ID&\
client_secret=$APP_SECRET&\
fb_exchange_token=$SHORT_TOKEN"
```

Te devuelve algo así:
```json
{"access_token":"EAA...long_lived...","token_type":"bearer","expires_in":5184000}
```

`5184000` segundos = 60 días. **Copiá ese token long-lived** — lo vas a usar como `IG_ACCESS_TOKEN`.

> ⚠️ El token caduca cada 60 días. Te conviene poner un recordatorio en el calendario para regenerarlo (o automatizar la renovación; lo dejo para más adelante).

## Paso 6: Obtener el Instagram Business Account ID

```bash
TOKEN="el token long-lived"

# Primero, ID de tu FB Page
curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=$TOKEN"
# Te devuelve un array con tus pages. Copiá el "id" de la que vinculaste a IG.

PAGE_ID="..."

# Ahora, el IG Business Account ID asociado a esa page
curl -s "https://graph.facebook.com/v21.0/$PAGE_ID?fields=instagram_business_account&access_token=$TOKEN"
# Te devuelve: {"instagram_business_account": {"id":"178..."}, ...}
```

**Copiá el `id`** del `instagram_business_account` — lo vas a usar como `IG_USER_ID`.

## Paso 7: Cargar los secrets en GitHub

1. https://github.com/allerand/cines/settings/secrets/actions
2. **New repository secret** (× 2):
   - Name: `IG_USER_ID` → Value: el ID del paso 6
   - Name: `IG_ACCESS_TOKEN` → Value: el token long-lived del paso 5
3. **Add secret** en cada uno

## Paso 8: Probar

Andá a https://github.com/allerand/cines/actions → **Scrape cartelera** → **Run workflow**.

En el log del job, después de "Post to Instagram" deberías ver:
```
✅ posteado — IG media id: 1789...
```

Y en @sitedigocine vas a ver el carrusel del día.

## Probar localmente sin GitHub Actions

```bash
export IG_USER_ID="178..."
export IG_ACCESS_TOKEN="EAA...long_lived..."
export PUBLIC_BASE_URL="https://raw.githubusercontent.com/allerand/cines/main"

# Dry run (solo loguea, no postea)
python3 scripts/post_to_instagram.py --date 2026-05-11 --dry-run

# Posteo real
python3 scripts/post_to_instagram.py --date 2026-05-11
```

## Renovación del token — AUTOMÁTICA (recomendado)

El workflow `.github/workflows/refresh-ig-token.yml` renueva el token solo el
**1 y el 15 de cada mes**: intercambia el long-lived vigente por uno nuevo
(otros ~60 días) y actualiza el secret `IG_ACCESS_TOKEN`. Como el token dura 60
días y se refresca cada ~15, nunca llega a vencer.

Para activarlo, cargá 3 secrets más (una sola vez):

1. https://github.com/allerand/cines/settings/secrets/actions → **New repository secret**:
   - `IG_APP_ID` → el App ID de Facebook (ej. `1296791348564477`)
   - `IG_APP_SECRET` → el App Secret (Meta → App settings → Basic → Mostrar)
2. Crear el **PAT** para que el workflow pueda escribir el secret:
   - https://github.com/settings/personal-access-tokens/new (fine-grained)
   - **Resource owner**: allerand · **Repository access**: sólo `allerand/cines`
   - **Permissions → Repository → Secrets**: **Read and write**
   - Generá el token y guardalo como secret `SECRETS_PAT` en el repo.
3. Probalo a mano: Actions → **Renovar token de Instagram** → **Run workflow**.
   Debería terminar con `✅ IG_ACCESS_TOKEN renovado y guardado`.

> El token nuevo se enmascara (`::add-mask::`) antes de usarse, así que no
> aparece en los logs. El PAT sólo puede tocar secrets de este repo.

## Renovación del token — MANUAL (fallback)

Si el auto-renovador falla o el token **ya venció** (hay que regenerarlo desde
cero en Meta), usá el helper local con un token corto recién generado:

```bash
APP_ID=... APP_SECRET=... SHORT_TOKEN=EAA... bash scripts/refresh_ig_token.sh
```

Copiá el token long-lived que imprime y pegalo en el secret `IG_ACCESS_TOKEN`.

## Troubleshooting

- **"Invalid OAuth access token"**: token caducado o malformado, regeneralo
- **"The user is not an Instagram Business Account"**: revisá el paso 1 y 2
- **"Image URL not accessible"**: GitHub raw URLs tardan unos segundos en propagarse después del push; el workflow ya espera 15s, podés subir el sleep si falla
- **Container queda en status_code=ERROR**: la imagen es muy grande o tiene formato inválido. Las PNGs generadas son 1080×1350 (portrait), que está dentro de los límites de IG
