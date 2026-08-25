"""
Scrapers de cartelera para cines de arte de Buenos Aires.
Sala Lugones · Cacodelphia · Cine Lorca · Cine York · MALBA
"""

# El módulo usa `X | Y` en anotaciones, que en 3.9 explota al importar con un
# "unsupported operand type(s) for |" que no menciona versiones. Esto deja las
# anotaciones sin evaluar (PEP 563) y hace que importe también en 3.9 — útil
# porque el python3 que trae macOS de fábrica sigue siendo viejo. El CI corre
# 3.11 y no cambia nada para él.
from __future__ import annotations

import re
import os
import json
import time
import base64
import imaplib
import email
import email.policy
import email.utils
import unicodedata
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Page

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MESES_ES = {
    "ene": 1, "enero": 1,   "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,   "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,   "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}

DIAS_ES = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4,
    "sábados": 5, "sabados": 5, "sábado": 5, "sabado": 5,
    "domingos": 6, "domingo": 6,
}


@dataclass
class Screening:
    cine: str
    title: str          # título en español (del cine)
    fecha: str          # YYYY-MM-DD
    hora: str           # HH:MM
    ticket_url: str = ""
    ciclo: str = ""     # nombre del ciclo/programa (si aplica)
    # Metadata desde la fuente original del cine (preferido sobre Letterboxd):
    director: str = ""
    country: str = ""
    year: Optional[int] = None
    duration: Optional[int] = None  # minutos
    original_title: str = ""        # útil como hint para IMDb/Letterboxd


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def fetch_bytes(url: str, timeout: int = 20, intentos: int = 3) -> bytes:
    """GET con reintentos. Un timeout suelto no puede costar un cine entero.

    Los scrapers atrapan sus excepciones y devuelven [], y salvo comerciales y
    Borges nada preserva las funciones de la corrida anterior: un fetch que
    falla una vez borra la sala de la web hasta el día siguiente. Pasó con
    Amorina el 3/8/2026 (schedule.json tenía las tres funciones de La Flor y la
    web las perdió). Tres intentos con backoff cubren el hipo de red típico;
    una fuente realmente caída sigue fallando y eso lo levanta la auditoría.
    """
    ultimo: Exception | None = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            ultimo = e
            if i < intentos - 1:
                time.sleep(2 ** i)      # 1s, 2s
    raise ultimo if ultimo else RuntimeError(f"fetch falló: {url}")


def fetch_html(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_bytes(url).decode("utf-8", errors="replace"), "html.parser")


# Cloudflare no siempre bloquea con un 403: el challenge ("Just a moment…")
# viene con 200 y su propio HTML, así que un fetch "exitoso" puede no traer una
# sola línea del sitio. Hay que mirar el cuerpo, no el status.
_CF_CHALLENGE_RE = re.compile(
    r"Just a moment|Performing security verification|challenge-platform|"
    r"cf-browser-verification|__cf_chl|Enable JavaScript and cookies to continue",
    re.IGNORECASE)


# El proxy contesta con SU propio status cuando el problema es la cuenta y no el
# sitio: 401 = key inválida o revocada, 402/403 = sin créditos o el plan no
# cubre lo que se pidió (ultra_premium, geotargeting). Reintentar no sirve —ni
# pedir otra geo—: hasta que no se renueve la key todas las bajadas por proxy
# van a fallar igual. Y el log tiene que decirlo, porque "no se pudo traer" a
# secas hace pensar que el que se puso duro es el cine.
def _credencial_del_proxy_caida(e: object) -> bool:
    return getattr(e, "code", None) in (401, 402, 403)


def _pista_credencial(e: object) -> str:
    if not _credencial_del_proxy_caida(e):
        return ""
    return (" — el que rechaza es el PROXY, no el sitio: renová SCRAPER_KEY "
            "(o BORGES_SCRAPER_KEY) o fijate los créditos del plan")


def _scraper_proxy_url(target: str, pais: str = "") -> Optional[str]:
    """Envuelve la URL objetivo en un servicio de scraping con IPs residenciales
    para saltear el bloqueo de Cloudflare a la IP del runner. Requiere el secret
    SCRAPER_KEY (o BORGES_SCRAPER_KEY, el nombre viejo: es el que está cargado en
    el repo, de cuando esto lo usaba sólo el Borges). Por defecto usa el formato
    de ScraperAPI (ultra_premium = residencial + anti-Cloudflare); se puede
    cambiar de proveedor con SCRAPER_URL_TEMPLATE, p.ej. scrape.do:
        https://api.scrape.do/?token={key}&super=true&url={url}

    `pais` pide que la IP sea de ese país (ISO-2). Los sitios del Estado suelen
    bloquear por geografía además de por datacenter: palaciolibertad.gob.ar
    contesta normal desde una conexión argentina y con 403 desde el runner, y el
    proxy —que sale por EE.UU. por defecto— devolvía 502 al intentar bajarlo.
    Cada proveedor lo pide con su propio parámetro; se agregan sólo si el
    template no los trae ya, así un template propio sigue mandando.
    """
    # La key y el template se toman EN PAR, nunca cruzados: son de un proveedor
    # puntual. Una key nueva en SCRAPER_KEY combinada con el template viejo de
    # BORGES_SCRAPER_URL_TEMPLATE (otro proveedor) da 401 Unauthorized, que se
    # lee igual que una key vencida y manda a buscar el problema al lado
    # equivocado.
    key = os.environ.get("SCRAPER_KEY")
    tmpl = os.environ.get("SCRAPER_URL_TEMPLATE")
    if not key:
        key = os.environ.get("BORGES_SCRAPER_KEY")
        tmpl = os.environ.get("BORGES_SCRAPER_URL_TEMPLATE")
    if not key:
        return None
    tmpl = tmpl or "https://api.scraperapi.com/?api_key={key}&ultra_premium=true&url={url}"
    proxy = tmpl.format(key=urllib.parse.quote(key, safe=""),
                        url=urllib.parse.quote(target, safe=""))
    if pais:
        if "scraperapi" in proxy and "country_code=" not in proxy:
            proxy += f"&country_code={pais}"
        elif "scrape.do" in proxy and "geoCode=" not in proxy:
            proxy += f"&geoCode={pais}"
            if "super=" not in proxy:
                proxy += "&super=true"   # scrape.do exige super para geo
    return proxy


def fetch_html_cf(url: str, contexto: str = "") -> Optional[BeautifulSoup]:
    """fetch_html para los sitios que están detrás de Cloudflare.

    Primero va directo (desde una IP argentina normal alcanza). Si el sitio
    responde con error o con el challenge, reintenta por el servicio de scraping
    residencial. Devuelve None cuando no hay forma: el scraper que llama corta y
    el cine queda vacío, pero con un motivo impreso en el log en vez del cero
    mudo que había antes.
    """
    html_txt = ""
    directo_err: Optional[object] = None
    try:
        html_txt = fetch_bytes(url).decode("utf-8", errors="replace")
    except Exception as e:
        directo_err = e
    if html_txt and not _CF_CHALLENGE_RE.search(html_txt[:4000]):
        return BeautifulSoup(html_txt, "html.parser")

    motivo = directo_err or "Cloudflare contestó el challenge («Just a moment…»)"
    etiqueta = contexto or url
    if not _scraper_proxy_url(url):
        print(f"  · ❌ [{etiqueta}] bloqueado: {motivo} "
              f"(configurá SCRAPER_KEY para un proxy residencial)")
        return None
    # Dos pasadas por el proxy, no dos iguales: primero pidiendo IP argentina
    # —el 502 del 16/8/2026 contra palaciolibertad.gob.ar salía de intentarlo
    # desde EE.UU.— y después sin geo, que es lo que ya funcionaba para el
    # Borges y lo único que anda si el plan del proveedor no incluye
    # geotargeting a la Argentina. El servicio tarda 60-90s en resolver el
    # challenge, así que el timeout va amplio.
    proxy_err: Optional[object] = None
    pista = ""
    for pais in ("ar", ""):
        proxy = _scraper_proxy_url(url, pais)
        try:
            txt = fetch_bytes(proxy, timeout=120, intentos=1).decode("utf-8", errors="replace")
        except Exception as e:
            proxy_err = f"{e} (IP {pais or 'default'})"
            if _credencial_del_proxy_caida(e):
                pista = _pista_credencial(e)
                break          # la segunda pasada iba a dar exactamente lo mismo
            continue
        if not _CF_CHALLENGE_RE.search(txt[:4000]):
            return BeautifulSoup(txt, "html.parser")
        proxy_err = f"el proxy también recibió el challenge (IP {pais or 'default'})"
    print(f"  · ❌ [{etiqueta}] no se pudo traer "
          f"(directo: {motivo}; proxy: {proxy_err}){pista}")
    return None


async def load_page(page: Page, url: str, wait_ms: int = 2500) -> BeautifulSoup:
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(wait_ms)
    return BeautifulSoup(await page.content(), "html.parser")


def future_weekday_dates(weekday: int, semanas: int = 2) -> list[date]:
    today = date.today()
    end = today + timedelta(weeks=semanas)
    result, d = [], today
    while d <= end:
        if d.weekday() == weekday:
            result.append(d)
        d += timedelta(days=1)
    return result


def parse_date_ddmm(text: str) -> Optional[str]:
    today = date.today()
    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", text)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = today.year
    if m.group(3):
        y = int(m.group(3))
        year = y + 2000 if y < 100 else y
    try:
        d = date(year, month, day)
        if d < today - timedelta(days=60):
            d = date(year + 1, month, day)
        return d.isoformat()
    except ValueError:
        return None


def parse_time_str(text: str) -> Optional[str]:
    # "15:00 h." or "18:00" or "18.30 h"
    m = re.search(r"\b(\d{1,2})[:\.](\d{2})\s*h?", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# MALBA  (malba.org.ar — WordPress/Elementor, sin bot-check con requests)
# ---------------------------------------------------------------------------

# Mapeo de día de semana en MALBA → weekday() de date (Lunes=0)
MALBA_DOW = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    "lunes,": 0, "martes,": 1, "miércoles,": 2, "miercoles,": 2,
    "jueves,": 3, "viernes,": 4, "sábado,": 5, "sabado,": 5, "domingo,": 6,
}


# Ciclos MALBA conocidos — usados para detectar el ciclo desde la página de evento
MALBA_KNOWN_CICLOS = (
    "Cineclub Nocturna",
    "Revista Caligari",
    "Generación del 60",
)


def fetch_malba_evento_meta(url: str) -> dict:
    """
    Extrae {director, ciclo} desde una página /evento/ de malba.org.ar.

    Patrones observados (en el texto plano):
      Ciclos:       "...Películas → 2026 [Ciclo ]CICLO_NAME FILM De DIRECTOR DAY..."
                    "...Cineclub Nocturna FILM De DIRECTOR Sábado 16 de mayo..."
      Standalone:   "FILM De DIRECTOR Domingo a las 18:00 ..."
    """
    if not url:
        return {}
    try:
        soup = fetch_html(url)
    except Exception:
        return {}
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    out: dict = {}

    # Director: "De NAME" antes de un día de semana (formato MALBA estándar).
    # MALBA repite el crédito N veces en algunas páginas ("De Christopher Nolan
    # De Christopher Nolan De Christopher Nolan Jueves…" en /evento/la-odisea/),
    # y el no-greedy se las tragaba todas. El (?:\s+De\s+\1)* consume esas
    # repeticiones FUERA del grupo: sólo colapsa si el crédito es idéntico, así
    # que un apellido con De propio ("Brian De Palma") sigue entero.
    md = re.search(
        r"\bDe\s+([A-ZÁÉÍÓÚÑ][^.\n]{2,60}?)(?:\s+De\s+\1)*\s+"
        r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|"
        r"Viernes|S[áa]bado|Domingo)",
        text,
    )
    if md:
        out["director"] = md.group(1).strip().rstrip(",")

    # Ciclo: dinámico — el <p> inmediatamente previo al <h1> del título contiene
    # el nombre del ciclo (ej. "Semana de cine portugués", "Cineclub Nocturna",
    # "Revista Caligari"). Esto evita tener que hardcodear nombres nuevos.
    h1 = soup.find("h1")
    title_text = h1.get_text(strip=True) if h1 else ""
    if h1:
        prev = h1
        for _ in range(12):
            prev = prev.find_previous()
            if prev is None:
                break
            if prev.name != "p":
                continue
            ct = prev.get_text(strip=True)
            # Filtros: no vacío, distinto del título, longitud razonable
            if not ct or ct == title_text or len(ct) > 80:
                continue
            out["ciclo"] = ct
            break

    # Fallback hardcoded (compat con flujo viejo, por si el HTML cambia)
    if "ciclo" not in out:
        for ciclo in MALBA_KNOWN_CICLOS:
            if title_text and re.search(re.escape(ciclo) + r"\s+" + re.escape(title_text), text):
                out["ciclo"] = ciclo
                break
            if "director" in out and re.search(
                re.escape(ciclo) + r"[^.]{0,200}\bDe\s+" + re.escape(out["director"]), text
            ):
                out["ciclo"] = ciclo
                break

    return out


def scrape_malba_ciclos() -> list[dict]:
    """
    Scrapea malba.org.ar/cine/ para extraer programas con su tipo y horario.
    Devuelve [{tipo, name, weekdays:[0-6], hora:"HH:MM"}, ...] sólo para entradas
    que tengan horario regular (Sábados/Domingos a las HH:MM).
    Tipos: "Ciclo", "Proyecciones" → name es el ciclo. "Continúa" → name es el film.
    """
    try:
        soup = fetch_html("https://malba.org.ar/cine/")
    except Exception:
        return []

    out: list[dict] = []
    for h in soup.find_all(["h2", "h3"]):
        name = h.get_text(strip=True)
        if not name or name.lower() == "cine":
            continue
        # Look at surrounding container text for type + schedule
        ctx = h
        for _ in range(5):
            ctx = ctx.parent
            if not ctx:
                break
        ctx_text = ctx.get_text(" ", strip=True)[:400] if ctx else ""

        # Type label (Ciclo / Proyecciones / Continúa) appears before the heading text in ctx
        tipo = ""
        for t in ("Ciclo", "Proyecciones", "Continúa", "Continua"):
            if t in ctx_text and ctx_text.find(t) < ctx_text.find(name) + 20:
                tipo = "Continúa" if t.startswith("Continu") else t
                break
        if not tipo:
            continue

        # Schedule: "Sábados a las 20:00" / "Domingos a las 18:00" / "Viernes a las 18:40"
        # Plural ("Sábados") or singular - both common
        sched = re.search(
            r"(Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bados?|Domingos?)\s+a\s+las\s+(\d{1,2}):?(\d{2})?",
            ctx_text, re.IGNORECASE,
        )
        if not sched:
            continue
        dow_word = sched.group(1).lower().rstrip("s")  # "sábados" → "sábado"
        if dow_word not in MALBA_DOW:
            continue
        weekday = MALBA_DOW[dow_word]
        hour = int(sched.group(2))
        minute = int(sched.group(3)) if sched.group(3) else 0
        hora = f"{hour:02d}:{minute:02d}"
        out.append({"tipo": tipo, "name": name, "weekday": weekday, "hora": hora})
    return out


# --- Ciclos de MALBA: páginas /evento/ con bloque "Programación" ------------
# La agenda día-a-día se pierde funciones de ciclos (Revista Caligari, etc.).
# Cada ciclo tiene una página /evento/ con un bloque "Programación" que lista
# "VIERNES 3 / 22:00 Family portrait, de Lucy Kerr". Lo parseamos aparte.
_MALBA_WD_RE = r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo"
_MALBA_WD = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
_MALBA_ACCENTS = str.maketrans("áéíóú", "aeiou")
_MALBA_EVT_RE = re.compile(
    rf"({_MALBA_WD_RE})\s+(\d{{1,2}})\s+(\d{{1,2}}):(\d{{2}})\s+"
    rf"(.+?)(?:,\s*de\s+([^,]+?))?"
    rf"(?=\s+(?:{_MALBA_WD_RE})\s+\d{{1,2}}\s+\d{{1,2}}:\d{{2}}|$)",
    re.IGNORECASE,
)


def _malba_wd(w: str) -> Optional[int]:
    # .lower() ANTES de translate: la tabla de acentos es sólo minúsculas, así
    # que un "SÁBADO" en mayúsculas hay que bajarlo primero o la Á no se saca.
    return _MALBA_WD.get(w.lower().translate(_MALBA_ACCENTS)[:3])


def _malba_resolve_date(weekday: Optional[int], day: int,
                        today: date, cutoff: date) -> Optional[date]:
    """(díasemana, díadelmes) → fecha concreta: el mes cercano donde el weekday
    coincide y cae en la ventana (desambigua el cruce de mes)."""
    if weekday is None:
        return None
    y, m = today.year, today.month
    for _ in range(5):
        try:
            cand = date(y, m, day)
        except ValueError:
            cand = None
        if cand and cand.weekday() == weekday and today <= cand <= cutoff:
            return cand
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return None


# Header de día dentro de la Programación: "JUEVES 9" / "SÁBADO 1 de agosto".
_MALBA_DAY_HEAD_RE = re.compile(
    r"^(" + _MALBA_WD_RE + r")\s+(\d{1,2})(?:\s+de\s+\w+)?$", re.IGNORECASE)
# Línea de función: "18:30 Título, de Director" (director opcional).
_MALBA_FILM_LINE_RE = re.compile(r"^(\d{1,2}):(\d{2})\s+(.+)$")


def _parse_malba_evento(soup, url: str, today: date, cutoff: date) -> list[Screening]:
    """Parsea la página /evento/ de un ciclo de MALBA: nombre del ciclo + bloque
    'Programación'. La grilla lista por día una o VARIAS funciones; sólo la
    primera de cada día trae el encabezado "JUEVES 9", las siguientes son sólo
    "20:30 …", así que arrastramos el día actual entre líneas/párrafos.
    """
    text = soup.get_text(" ", strip=True)
    mc = re.search(r"Ciclo\s+(.+?)\s+(?:" + _MALBA_WD_RE + r")\s+a\s+las",
                   text, re.IGNORECASE)
    if mc:
        ciclo = mc.group(1).strip()
    else:
        # Sin "Ciclo X ... a las" (ej. "Trasnoches / Orson Welles x4"): usamos el
        # título del evento como nombre del ciclo ("Orson Welles x4", "Cineclub
        # Nocturna", "Lita Stantic: no habrá nadie igual").
        h1 = soup.find("h1")
        ciclo = h1.get_text(strip=True) if h1 else ""
    # Director del ciclo para retrospectivas de un solo autor (ej. "Orson Welles
    # x4"), donde la Programación lista la película SIN ", de Director". Se toma
    # del copete ("...la obra de NOMBRE...") o del título del ciclo ("NOMBRE xN").
    cycle_director = ""
    _cd = re.search(
        r"(?:(?:la\s+)?obra\s+de|retrospectiva(?:\s+de|\s+dedicad[oa]\s+a)|"
        r"homenaje\s+a|dedicad[oa]\s+a(?:\s+la\s+obra\s+de)?)\s+"
        r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*){0,3})",
        text,
    ) or re.search(
        r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*){0,3})\s+x\s*\d+\b",
        text,
    )
    if _cd:
        cycle_director = _cd.group(1).strip().rstrip(".,")

    h3 = next((h for h in soup.find_all(["h3", "h2"])
               if h.get_text(strip=True).lower().startswith("programaci")), None)
    if h3 is None:
        return []

    out: list[Screening] = []
    seen: set = set()
    cur: Optional[tuple[Optional[int], int]] = None  # (weekday, día del mes)
    for p in h3.find_all_next("p"):
        for br in p.find_all("br"):
            br.replace_with("\n")
        lines = [ln.strip() for ln in p.get_text().split("\n") if ln.strip()]
        if not lines:
            continue
        # ¿Primera línea es encabezado de día? (setea el día actual)
        dh = _MALBA_DAY_HEAD_RE.match(lines[0])
        start = 0
        if dh:
            cur = (_malba_wd(dh.group(1)), int(dh.group(2)))
            start = 1
        elif not _MALBA_FILM_LINE_RE.match(lines[0]):
            # <p> ajeno a la programación (botón "Comprar entradas" / pie):
            # si ya juntamos funciones, es el fin de la sección.
            if out or "Comprar entradas" in lines[0]:
                break
            continue
        for ln in lines[start:]:
            fm = _MALBA_FILM_LINE_RE.match(ln)
            if not fm or cur is None:
                continue
            d = _malba_resolve_date(cur[0], cur[1], today, cutoff)
            if not d:
                continue
            hora = f"{int(fm.group(1)):02d}:{fm.group(2)}"
            rest = fm.group(3).strip()
            if ", de " in rest:
                title, director = rest.rsplit(", de ", 1)
                title, director = title.strip().rstrip(","), director.strip().rstrip(".")
            else:
                title, director = rest.strip().rstrip(","), cycle_director
            key = (title, d.isoformat(), hora)
            if not title or key in seen:
                continue
            seen.add(key)
            out.append(Screening(cine="MALBA", title=title, fecha=d.isoformat(),
                                 hora=hora, ticket_url=url, ciclo=ciclo,
                                 director=director))
    return out


def scrape_malba_eventos(today: date, cutoff: date) -> list[Screening]:
    """Recorre los ciclos linkeados en malba.org.ar/cine/ y parsea el bloque
    'Programación' de cada página /evento/."""
    try:
        soup = fetch_html("https://malba.org.ar/cine/")
    except Exception:
        return []
    urls: list[str] = []
    seen_u: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"/evento/")):
        u = a.get("href", "")
        if not u:
            continue
        if not u.startswith("http"):
            u = "https://malba.org.ar" + ("" if u.startswith("/") else "/") + u
        u = u.split("?")[0].split("#")[0].rstrip("/")
        if u not in seen_u:
            seen_u.add(u)
            urls.append(u)
    out: list[Screening] = []
    for u in urls[:40]:
        try:
            esoup = fetch_html(u)
        except Exception:
            continue
        out.extend(_parse_malba_evento(esoup, u, today, cutoff))
    return out


def scrape_malba(semanas: int = 2) -> list[Screening]:
    today = date.today()
    end = today + timedelta(weeks=semanas)
    result: list[Screening] = []
    seen: set[tuple] = set()

    # Ciclos vía páginas /evento/ PRIMERO: traen título/director/ciclo limpios
    # del bloque "Programación". Son la fuente autoritativa para esas películas,
    # así que después la agenda día-a-día NO las vuelve a agregar (evita
    # duplicados tipo "Family Portrait" y directores sucios).
    covered_ciclo: set[tuple] = set()

    def _mnorm(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()

    try:
        for s in scrape_malba_eventos(today, end):
            key = (s.title, s.fecha, s.hora)
            if key in seen:
                continue
            seen.add(key)
            covered_ciclo.add((_mnorm(s.title), s.fecha))
            result.append(s)
    except Exception:
        pass

    # Build (weekday, hora) → ciclo_name map for cycles/series; standalone films
    # ("Continúa") populate it for completeness but we won't tag those as ciclo.
    ciclo_map: dict[tuple[int, str], str] = {}
    try:
        for entry in scrape_malba_ciclos():
            if entry["tipo"] in ("Ciclo", "Proyecciones"):
                ciclo_map[(entry["weekday"], entry["hora"])] = entry["name"]
    except Exception:
        pass

    d = today
    while d <= end:
        url = f"https://malba.org.ar/agenda/on/{d.year}/{d.month:02d}/{d.day:02d}/"
        try:
            soup = fetch_html(url)
        except Exception:
            d += timedelta(days=1)
            continue

        for span in soup.find_all("span", class_="elementor-post-info__item--type-custom"):
            text = span.get_text(strip=True)
            if "Cine" not in text:
                continue

            # Parse the time from the span text (e.g. "18:40 Cine")
            time_m = re.match(r"(\d{1,2}:\d{2})", text)
            hora = f"{int(time_m.group(1).split(':')[0]):02d}:{time_m.group(1).split(':')[1]}" if time_m else "??"

            # Card = el ancestro MÁS CERCANO que tiene un título. El link a
            # /evento/ es opcional: MALBA no lo pone en todas las funciones
            # (p.ej. "Cordero de Dios" no es clickeable) y antes ésas se
            # perdían por exigir link+título. Tomar el ancestro más cercano
            # evita agarrar un contenedor con varias cards (título equivocado).
            card = None
            node = span.parent
            for _ in range(15):
                if node is None:
                    break
                if node.find(class_=re.compile(r"post-title|page-title|entry-title")):
                    card = node
                    break
                node = node.parent

            if card is None:
                continue

            link = card.find("a", href=re.compile(r"/evento/"))
            title_el = card.find(class_=re.compile(r"post-title|page-title|entry-title"))
            ticket_url = link["href"] if link else "https://malba.org.ar/cine/"
            title = title_el.get_text(strip=True) if title_el else ""

            if not title:
                continue
            # Skip ciclo cards (ej "Generación del 60") — sus pelis individuales
            # aparecen por separado en otros cards
            if title in MALBA_KNOWN_CICLOS:
                continue
            # Ya la trajo (más limpia) el scrape de ciclos /evento/ ese día.
            if (_mnorm(title), d.isoformat()) in covered_ciclo:
                continue

            # Clave normalizada (case-insensitive) para que la misma función no
            # se duplique cuando la agenda y la Programación del ciclo la
            # escriben con distinto casing ("Family Portrait" vs "Family portrait").
            key = (re.sub(r"\s+", " ", title).strip().lower(), d.isoformat(), hora)
            if key not in seen:
                seen.add(key)
                # Fallback ciclo desde matching weekday+hora (cobertura inicial)
                ciclo = ciclo_map.get((d.weekday(), hora), "")
                result.append(Screening(
                    cine="MALBA",
                    title=title,
                    fecha=d.isoformat(),
                    hora=hora,
                    ticket_url=ticket_url,
                    ciclo=ciclo,
                ))

        d += timedelta(days=1)

    # Enriquecer cada función con director / ciclo desde su página de evento.
    # Múltiples funciones de un mismo título comparten ticket_url → cache por URL.
    meta_cache: dict[str, dict] = {}
    for s in result:
        if not s.ticket_url:
            continue
        if s.ticket_url not in meta_cache:
            meta_cache[s.ticket_url] = fetch_malba_evento_meta(s.ticket_url)
        meta = meta_cache[s.ticket_url]
        if meta.get("director") and not s.director:
            s.director = meta["director"]
        if meta.get("ciclo") and not s.ciclo:
            s.ciclo = meta["ciclo"]

    return result


# ---------------------------------------------------------------------------
# Sala Lugones  (complejoteatral.gob.ar → entradasba.buenosaires.gob.ar)
# ---------------------------------------------------------------------------

def fetch_ctba_ver_page_sync(ver_url: str) -> Optional[str]:
    """Carga la página /ver/ vía HTTP (no playwright) y devuelve texto plano.

    Usamos urllib porque playwright headless se viene quedando sin contenido en
    los runners de GH Actions (devuelve ~299B en vez de 90KB — bot-detection
    o render incompleto). El HTML servido por el server tiene todo el contenido
    estático, así que un fetch directo es más rápido y más confiable.

    Las URLs de complejoteatral.gob.ar suelen tener ñ/ó/í/:/espacios en el path —
    hace falta percent-encoding manual antes de pegar a urllib.
    """
    # Percent-encode el path (preservando : / - , ya válidos en URLs)
    parts = urllib.parse.urlsplit(ver_url)
    safe_path = urllib.parse.quote(parts.path, safe="/-:,")
    encoded = urllib.parse.urlunsplit((parts.scheme, parts.netloc, safe_path, parts.query, parts.fragment))
    try:
        req = urllib.request.Request(encoded, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    soup = BeautifulSoup(html, "html.parser")
    # get_text con "\n" preserva la estructura por bloque/párrafo, que es lo
    # que parse_ctba_program_text espera.
    raw = soup.get_text("\n")
    return "\n".join(re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines() if ln.strip())
def is_ctba_estreno_page(text: str) -> bool:
    return bool(re.search(r"\bEstreno\s+exclusivo\b", text, re.IGNORECASE))

def parse_ctba_estreno_page(text: str) -> dict:
    """
    Parsea la página /ver/ de un estreno (no ciclo). Patrón típico del bloque
    de metadata:
      "Título original: Mo shi lu  Título internacional: Stranger Eyes
       Singapur, Taiwán, Francia, Estados Unidos  2024  Mandarín  Color  126'
       – DCP 2K  Dirección y guion: Yeo Siew Hua  Producción: ..."

    Estrategia: localizar el bloque metadata acotado entre "Título original:"
    (o el principio) y "Dirección" — todo lo importante está ahí.
    """
    out: dict = {}

    # Localizar el bloque metadata: entre "Título original" (o inicio) y "Dirección"
    dir_idx = re.search(r"Direcci[óo]n(?:\s+y\s+gui[óo]n)?\s*:", text)
    block_end = dir_idx.start() if dir_idx else len(text)
    to_idx = text.find("Título original")
    if to_idx < 0:
        to_idx = text.find("Titulo original")
    block_start = to_idx if to_idx >= 0 else max(0, block_end - 400)
    block = text[block_start:block_end]

    # Original / international titles (consumen su propio segmento)
    mo = re.search(r"T[íi]tulo original\s*:\s*([^\n]+?)\s+(?:T[íi]tulo internacional|[A-ZÁÉÍÓÚÑ])", block)
    if mo:
        out["original_title"] = mo.group(1).strip().rstrip(",;:.")
    # Quitamos esos labels del bloque para que no contaminen la detección de país
    cleaned = re.sub(r"T[íi]tulo (?:original|internacional)\s*:\s*[^\n]+?(?=\s+(?:T[íi]tulo|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:,|\s+\d{4})))", "", block)

    # Year
    my = re.search(r"\b(19\d{2}|20\d{2})\b", cleaned)
    if my:
        out["year"] = int(my.group(1))
        # País: segmento inmediatamente antes del año — palabras Capitalizadas separadas por coma
        before = cleaned[max(0, my.start() - 120):my.start()].rstrip()
        # Capturar la lista de países al final (uno o más, separados por coma)
        cm = re.search(
            r"((?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)*)"
            r"(?:\s*,\s*[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)*)*)\s*$",
            before,
        )
        if cm:
            countries = [c.strip() for c in cm.group(1).split(",") if c.strip()]
            if 1 <= len(countries) <= 5:
                out["country"] = ", ".join(countries[:4])

    # Duración: "126'" o "126 min" dentro del bloque metadata (no en sinopsis)
    md_dur = re.search(r"\b(\d{2,3})\s*['′]\s*(?:–|-|\s|$)", cleaned) or \
             re.search(r"\b(\d{2,3})\s*min\b", cleaned)
    if md_dur:
        out["duration"] = int(md_dur.group(1))

    # Director (busca en todo el text, no sólo en el block)
    md = re.search(
        r"Direcci[óo]n(?:\s+y\s+gui[óo]n)?\s*:\s*([^\n.]+?)(?:\s+(?:Producci[óo]n|Gui[óo]n|Fotograf[íi]a|Con|Producido|Sonido|Montaje|Reparto|M[úu]sica|Edici[óo]n|$))",
        text,
    )
    if md:
        out["director"] = md.group(1).strip().rstrip(",")

    return out


def parse_ctba_grouped_dates_event(text: str) -> dict:
    """
    Maneja eventos del CTBA con formato:
        TITULO
        DIRECTOR(es)
        Estreno
        ...
        TITULO (AÑO)
        DíaSemana N[, día N]... [y día N,] HH(.MM|:MM)? horas
        ...

    Devuelve {director, year, country, dates: [(date, "HH:MM"), ...]} o {}.
    Útil para estrenos como 'La noche está marchándose ya' que no usan el
    bloque "Título original / Dirección" sino fechas agrupadas.
    """
    out: dict = {"dates": []}

    # Año y título: línea final "TÍTULO (YYYY)" antes de la lista de fechas
    ty = re.search(r"^([A-ZÁÉÍÓÚÑ][^\n(]+?)\s*\((\d{4})\)\s*$", text, re.MULTILINE)
    if ty:
        out["year"] = int(ty.group(2))

    # Director: línea inmediata previa al marcador "Estreno" (encabezado típico).
    # OJO: a veces esa línea es una nota del cupo ("Siete únicas funciones") y no
    # el director — la descartamos para no ensuciar el campo (el enrichment /
    # override lo completa bien).
    dm = re.search(r"\n([A-ZÁÉÍÓÚÑ][^\n]+?)\s*\nEstreno(?:\s|\n)", text)
    if dm:
        cand = re.sub(r"\s+", " ", dm.group(1)).strip()
        if not re.search(r"funci[óo]n|[úu]nicas?|estreno|presenta|exclusiv|anticipo|\bciclo\b",
                         cand, re.IGNORECASE):
            out["director"] = cand

    # Mes contextual: buscar "de MES" cerca del primer "Del N al N de MES" o
    # "a partir del DíaSemana N de MES".
    month: Optional[int] = None
    mm = re.search(
        r"(?:Del\s+\d+\s+al\s+\d+|a\s+partir\s+del\s+\w+\s+\d+)\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)",
        text, re.IGNORECASE,
    )
    if mm:
        month = MESES_ES.get(mm.group(1).lower())
    if month is None:
        # Fallback: primer "de MES" en todo el texto
        m2 = re.search(
            r"\bde\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
            text, re.IGNORECASE,
        )
        if m2:
            month = MESES_ES.get(m2.group(1).lower())
    if month is None:
        return out

    # Año contextual: si no salió del título-año, usar año actual y avanzar si el
    # mes contextual ya pasó este año
    year = out.get("year") or date.today().year
    today = date.today()
    if year < today.year:
        # Película de archivo: la programación es para el año actual o siguiente
        year = today.year
    if year == today.year and month < today.month:
        year += 1

    # Líneas tipo "Jueves 4, viernes 5 y sábado 6, 20.30 horas"
    date_line_re = re.compile(
        r"((?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+\d+"
        r"(?:\s*[,y]+\s*(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+\d+)*)"
        r"\s*,?\s+(\d{1,2})(?:[.:](\d{2}))?\s+horas?",
        re.IGNORECASE,
    )
    for m in date_line_re.finditer(text):
        days_str = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        # Extraer todos los números de día del segmento
        day_nums = [int(d) for d in re.findall(r"\d+", days_str)]
        for dn in day_nums:
            try:
                d = date(year, month, dn)
                out["dates"].append((d, f"{hour:02d}:{minute:02d}"))
            except ValueError:
                pass

    return out


def parse_ctba_program_text(normalized: str) -> dict[tuple[int, str], list[dict]]:
    """
    Parsea texto plano de una página /ver/ de ciclo CTBA (Sala Lugones).
    Captura Título, Director y Duración (ej: 93').

    Devuelve {(día, hora): [película, ...]}: una MISMA función puede tener varias
    películas (p.ej. el Syncro Film Fest, donde cada programa son varios cortos),
    así que acumulamos una lista por horario en vez de pisar.
    """
    mapping: dict[tuple[int, str], list[dict]] = {}

    # Header de día: debe estar en su propia línea. Esto descarta las
    # menciones inline tipo "Del jueves 21 al martes 26 de mayo se proyecta..."
    # que aparecen en sinopsis y rompían el chunking.
    day_re = re.compile(
        r"\n(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\s+(\d{1,2})(?=\s*\n)",
    )
    # Bloques horarios. Soporta:
    #   A las 15 horas
    #   A las 15 y 21 horas
    #   A las 20.30 horas
    #   A las 15:30 horas
    #   A las 20.30 hs. / hs / h      ← la página los mezcla y antes no matcheaban
    #
    # Que una cabecera NO matchee no deja la función afuera: las películas que
    # venían abajo se le suman al bloque horario ANTERIOR, o sea que aparecen en
    # cartelera con el horario de otra función. Por eso conviene ser generoso acá.
    hour_re = re.compile(
        r"A las (\d{1,2})(?:[.:](\d{2}))?(?:\s+y\s+(\d{1,2})(?:[.:](\d{2}))?)?"
        r"\s*(?:horas?|hs\.?|h)\b",
        re.IGNORECASE,
    )
    # Cabecera del bloque-peli: TITLE en su propia línea, luego (paren con meta).
    # Soporta:
    #   (Original; País; Año)                ← variante "3 segmentos"
    #   (Original; País/Co-producción, Año)  ← idem, coma antes del año
    #   (País; Año)                          ← variante "2 segmentos" (sin original)
    #   (País/Co-producción, Año)            ← idem 2 seg, coma antes del año
    # Y tolera saltos de línea dentro del paréntesis.
    film_head_re = re.compile(
        r"^([A-ZÁÉÍÓÚÑ0-9][^\n(]+?)\s*\n+\(([^)]+?)\)",
        re.MULTILINE,
    )
    # Director: captura hasta el fin de línea para no cortar en abreviaturas
    # ("F. W. Murnau", "A. W. Sandberg", "Joseph L. Mankiewicz")
    director_re = re.compile(r"Direcci[óo]n[:\s]+([^\n]+)", re.IGNORECASE)
    # Duración: "(84'; DM)" — apóstrofes U+0027 / U+2019 / U+2032
    duration_re = re.compile("\\((\\d{2,3})\\s*['’′]")

    def _parse_paren_meta(paren: str) -> Optional[dict]:
        """De `(Sparrows; EE:UU; 1926)` o `(País; 1972)` extrae year/country/original.
        Rechaza paréntesis que tienen SOLO año tipo `(1966)` — son menciones
        espurias en sinopsis, no headers reales de película.
        """
        s = re.sub(r"\s+", " ", paren).strip()
        ym = re.search(r"(?:^|[;,])\s*(\d{4})\s*$", s)
        if not ym:
            return None
        year = int(ym.group(1))
        pre = s[: ym.start()].strip().rstrip(",;").strip()
        parts = [p.strip() for p in re.split(r"\s*;\s*", pre) if p.strip()]
        if not parts:
            return None  # `(1966)` suelto → mención en sinopsis, no header de peli
        out: dict = {"year": year}
        if len(parts) >= 2:
            out["original_title"] = parts[0]
            out["country"] = "; ".join(parts[1:])
        else:
            out["original_title"] = ""
            out["country"] = parts[0]
        return out

    parts = day_re.split(normalized)
    for i in range(1, len(parts), 2):
        day_num = int(parts[i])
        chunk = parts[i + 1] if i + 1 < len(parts) else ""

        hour_matches = list(hour_re.finditer(chunk))
        for idx, hm in enumerate(hour_matches):
            # group(1)=hh1, group(2)=mm1, group(3)=hh2, group(4)=mm2
            hh_mm: list[tuple[int, int]] = [(int(hm.group(1)), int(hm.group(2) or 0))]
            if hm.group(3):
                hh_mm.append((int(hm.group(3)), int(hm.group(4) or 0)))

            sub_start = hm.end()
            sub_end = hour_matches[idx + 1].start() if idx + 1 < len(hour_matches) else len(chunk)
            sub = chunk[sub_start:sub_end]

            # Etiqueta del programa: la línea justo antes de "A las X horas"
            # (p.ej. "Programa de apertura" en un festival de cortos). Sirve para
            # distinguir a qué función pertenece cada corto.
            region = chunk[(hour_matches[idx - 1].end() if idx > 0 else 0):hm.start()]
            prog_label = ""
            for ln in reversed(region.splitlines()):
                ln = ln.strip()
                if not ln:
                    continue
                # Saltear líneas que parezcan película (terminan en "(...año)") o
                # sinopsis larga; quedarnos con una etiqueta corta tipo "Programa X".
                # También saltear notas de formato/duración sueltas tipo "(93';
                # DM)." y encabezados de día ("Miércoles 1°", "Lunes 5") — no son
                # un nombre de programa, sólo metadata/fechas residuales.
                is_film_year = re.search(r"\([^)]*\d{4}[^)]*\)", ln)
                is_format_note = ln.startswith("(") or re.search(r"\d{2,3}\s*['’′]", ln)
                is_day_header = re.match(
                    r"^(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\b",
                    ln, re.IGNORECASE)
                if not is_film_year and not is_format_note and not is_day_header and len(ln) <= 60:
                    prog_label = ln
                break

            # Localizamos las cabeceras de peli; cada bloque horario suele
            # tener UNA peli, pero soportamos múltiples por las dudas.
            film_heads = list(film_head_re.finditer(sub))
            if not film_heads:
                continue
            for fi, fm in enumerate(film_heads):
                head_start = fm.start()
                head_end = (
                    film_heads[fi + 1].start() if fi + 1 < len(film_heads) else len(sub)
                )
                film_segment = sub[head_start:head_end]

                meta = _parse_paren_meta(fm.group(2))
                if not meta:
                    continue
                entry: dict = {
                    "title": fm.group(1).strip(),
                    "original_title": meta.get("original_title", ""),
                    "country": meta.get("country", ""),
                    "year": meta.get("year"),
                    "program": prog_label,
                }
                dm = director_re.search(film_segment)
                if dm:
                    d = re.sub(r"\s+", " ", dm.group(1)).strip()
                    # Quitar punto final y posibles "y guion: ..." final
                    d = re.sub(r"\s+y\s+gui[óo]n:.*$", "", d, flags=re.IGNORECASE)
                    entry["director"] = d.rstrip(".").strip()
                dur = duration_re.search(film_segment)
                if dur:
                    entry["duration"] = int(dur.group(1))

                for hh, mm in hh_mm:
                    mapping.setdefault((day_num, f"{hh:02d}:{mm:02d}"), []).append(entry)

    return mapping

async def scrape_lugones(page: Page) -> list[Screening]:
    """
    1. Lista eventos cine en complejoteatral.gob.ar/sala-leopoldo-lugones
    2. Para cada evento, scrapea la página de entradasba para obtener
       fechas y horarios exactos.
    3. Para eventos con ciclos (múltiples películas), parsea la página /ver/
       para extraer información de cada película del ciclo.
    """
    await page.goto(
        "https://complejoteatral.gob.ar/sala-leopoldo-lugones",
        wait_until="networkidle", timeout=30000,
    )
    await page.wait_for_timeout(3000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(2000)

    soup = BeautifulSoup(await page.content(), "html.parser")
    events: list[dict] = []

    for card in soup.select("div.list-item-programacion"):
        cat_el = card.select_one("span.category")
        if not cat_el or "cine" not in cat_el.get_text(strip=True).lower():
            continue

        title_el = card.select_one("h2.mango-grotesque")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        ver_link = card.select_one("a[href*='/ver/']")
        ver_url = ver_link["href"] if ver_link and ver_link.get("href") else ""
        if ver_url and not ver_url.startswith("http"):
            ver_url = "https://complejoteatral.gob.ar" + ver_url

        buy_link = card.select_one("a.button.buy")
        ticket_url = buy_link["href"] if buy_link and buy_link.get("href") else ""

        events.append({"title": title, "ticket_url": ticket_url, "ver_url": ver_url})

    result: list[Screening] = []
    today = date.today()
    cutoff = today + timedelta(days=60)

    for ev in events:
        cycle_name = ev["title"]
        ticket_url = ev["ticket_url"]
        ver_url = ev["ver_url"]

        # Fetch /ver/ page ONCE; try cycle-format parse, fallback to estreno parse
        program: dict[tuple[int, str], dict] = {}
        estreno_meta: dict = {}
        ver_text: Optional[str] = None
        looks_like_cycle: bool = False
        is_estreno: bool = False
        ver_text_len = 0
        n_hour_blocks = 0
        if ver_url:
            ver_text = fetch_ctba_ver_page_sync(ver_url)
            if ver_text:
                ver_text_len = len(ver_text)
                # Detectar estructura de ciclo: ≥2 bloques "A las X horas".
                # Si la página tiene forma de ciclo nunca debemos usar
                # cycle_name como título de la peli aunque el parser falle.
                hour_blocks = re.findall(
                    r"A las \d{1,2}(?:\s+y\s+\d{1,2})?\s+horas?",
                    ver_text, re.IGNORECASE,
                )
                n_hour_blocks = len(hour_blocks)
                looks_like_cycle = n_hour_blocks >= 2
                # "Estreno exclusivo" aparece tanto en estrenos genuinos como
                # en ciclos que acompañan a un estreno (ej Teresa Villaverde →
                # Justa). Heurística confiable: intentar parser de ciclo
                # primero. Si extrae películas, es ciclo. Si no, es estreno.
                program = parse_ctba_program_text(ver_text)
                if program:
                    is_estreno = False
                else:
                    is_estreno = True
                    estreno_meta = parse_ctba_estreno_page(ver_text)

        # Diagnóstico — muy útil para debuggear en runners
        print(
            f"  · {cycle_name[:50]:<50}  "
            f"ver_text={ver_text_len:>5}B  "
            f"hour_blocks={n_hour_blocks:>2}  "
            f"program={len(program):>2}  "
            f"estreno={'sí' if estreno_meta else 'no'}  "
            f"ciclo_visible={looks_like_cycle}",
            flush=True,
        )

        # Para ciclos (múltiples películas): construir fechas directamente desde el
        # programa, sin depender del entradasba ticket URL (que sólo cubre 1 film).
        if program and ver_text and not is_estreno:
            # El encabezado del ciclo puede abarcar DOS meses, p.ej.
            #   "Del jueves 23 de julio al domingo 2 de agosto".
            # El código viejo tomaba SÓLO el mes final ("agosto") con el regex
            # `al ... de (mes)` y lo aplicaba a TODOS los días → las funciones de
            # julio (23-31) quedaban en agosto y desaparecían de la cartelera de
            # la semana en curso ("falta todo el ciclo"). Ahora anclamos en el mes
            # INICIAL y recorremos los encabezados de día en su orden cronológico,
            # avanzando de mes cada vez que el número de día baja (rollover
            # julio→agosto, o de fin de año diciembre→enero).
            MONTH_RE = (
                r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto"
                r"|septiembre|setiembre|octubre|noviembre|diciembre)"
            )
            # Preferimos el mes que sigue al día inicial ("Del <díaSem> 23 de
            # julio ..."). Si el encabezado no lo nombra (formato de un solo mes,
            # "Del miércoles 6 al 27 de mayo"), caemos al mes final.
            anchor = re.search(
                r"\b[Dd]el\s+\w+\s+\d{1,2}\s+de\s+" + MONTH_RE + r"(?:\s+de\s+(\d{4}))?",
                ver_text, re.IGNORECASE,
            ) or re.search(
                r"\bal\s+\w+\s+\d{1,2}\s+de\s+" + MONTH_RE + r"(?:\s+de\s+(\d{4}))?",
                ver_text, re.IGNORECASE,
            )
            cycle_month: Optional[int] = None
            cycle_year: int = today.year
            if anchor:
                cycle_month = MESES_ES.get(anchor.group(1).lower())
                if anchor.group(2):
                    cycle_year = int(anchor.group(2))
            # Fallback: buscar cualquier mención de mes
            if not cycle_month:
                for m_name, m_num in MESES_ES.items():
                    if len(m_name) > 3 and m_name in ver_text.lower():
                        cycle_month = m_num
                        break

            if cycle_month:
                # Si el mes inicial ya pasó este año, la programación es del que
                # viene (archivo / programación adelantada).
                if cycle_year == today.year and cycle_month < today.month:
                    cycle_year += 1

                # Encabezados de día en el orden en que aparecen (cronológico).
                ordered_days = [
                    int(m.group(1)) for m in re.finditer(
                        r"\n(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[aá]bado|Domingo)"
                        r"\s+(\d{1,2})(?=\s*\n)",
                        ver_text,
                    )
                ]
                # Mapear cada día → (mes, año), avanzando de mes en cada bajada.
                day_to_ym: dict[int, tuple[int, int]] = {}
                cur_month, cur_year = cycle_month, cycle_year
                prev_day: Optional[int] = None
                for dnum in ordered_days:
                    if prev_day is not None and dnum < prev_day:
                        cur_month += 1
                        if cur_month > 12:
                            cur_month, cur_year = 1, cur_year + 1
                    day_to_ym.setdefault(dnum, (cur_month, cur_year))
                    prev_day = dnum

                for (day_num, hora), entries in program.items():
                    ym = day_to_ym.get(day_num, (cycle_month, cycle_year))
                    try:
                        d = date(ym[1], ym[0], day_num)
                    except ValueError:
                        continue
                    if d < today or d > cutoff:
                        continue
                    # Una función puede tener varias películas (cortos del mismo
                    # programa): emitimos una fila por cada una, misma fecha/hora.
                    for entry in entries:
                        # Ciclo + nombre del programa (ej. "Syncro Film Fest -
                        # Programa de apertura") para distinguir cada función.
                        prog = entry.get("program", "")
                        ciclo_label = f"{cycle_name} - {prog}" if prog else cycle_name
                        result.append(Screening(
                            cine="Sala Lugones",
                            title=entry["title"],
                            fecha=d.isoformat(), hora=hora,
                            ticket_url=ticket_url,
                            ciclo=ciclo_label,
                            director=entry.get("director", ""),
                            country=entry.get("country", ""),
                            year=entry.get("year"),
                            duration=entry.get("duration"),
                            original_title=entry.get("original_title", ""),
                        ))
            continue  # siguiente evento — no ir a entradasba

        # Antes del fallback "Sin fecha", probar parser de fechas-agrupadas
        # (estrenos como "La noche está marchándose ya" que listan
        # "Jueves 4, viernes 5 y sábado 6, 20.30 horas" en el /ver/ y todavía
        # no tienen entradas en entradasba).
        if ver_text and not program:
            sp = parse_ctba_grouped_dates_event(ver_text)
            sp_dates = sp.get("dates", [])
            if sp_dates:
                for d, hora in sp_dates:
                    if d < today or d > cutoff:
                        continue
                    result.append(Screening(
                        cine="Sala Lugones",
                        title=cycle_name,
                        fecha=d.isoformat(),
                        hora=hora,
                        ticket_url=ticket_url,
                        ciclo="Estreno",
                        director=sp.get("director", ""),
                        year=sp.get("year"),
                    ))
                continue

        if not ticket_url or "entradasba" not in ticket_url:
            result.append(Screening(
                cine="Sala Lugones", title=cycle_name,
                fecha="Sin fecha", hora="??", ticket_url=ticket_url,
            ))
            continue

        try:
            await page.goto(ticket_url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(2500)
            ticket_soup = BeautifulSoup(await page.content(), "html.parser")

            for fecha_card in ticket_soup.select("div.fecha-card"):
                day_el = fecha_card.select_one("div.dia-numero")
                month_el = fecha_card.select_one("div.dia-nombre")
                time_el = fecha_card.select_one("div.horario-unico")

                if not (day_el and month_el and time_el):
                    continue

                day = int(re.sub(r"\D", "", day_el.get_text()))
                month_str = month_el.get_text(strip=True).lower()[:3]
                month = MESES_ES.get(month_str)
                hora_raw = time_el.get_text(strip=True)

                if not month:
                    continue

                hora = parse_time_str(hora_raw) or "??"

                try:
                    d = date(today.year, month, day)
                    if d < today - timedelta(days=1):
                        d = date(today.year + 1, month, day)
                    if d > cutoff:
                        continue

                    if is_estreno:
                        # Película individual (estreno) — toda la metadata viene
                        # del /ver/ y el ciclo es "Estreno"
                        result.append(Screening(
                            cine="Sala Lugones",
                            title=cycle_name,  # acá title==film_name
                            fecha=d.isoformat(), hora=hora,
                            ticket_url=ticket_url,
                            ciclo="Estreno",
                            director=estreno_meta.get("director", ""),
                            country=estreno_meta.get("country", ""),
                            year=estreno_meta.get("year"),
                            duration=estreno_meta.get("duration"),
                        ))
                    elif looks_like_cycle:
                        # Página parece ciclo pero el parser falló — peli
                        # desconocida. Marcamos visible con ciclo "⚠️ parser
                        # falló" para que se note en la web y no se confunda
                        # con un estreno legítimo.
                        result.append(Screening(
                            cine="Sala Lugones", title=cycle_name,
                            fecha=d.isoformat(), hora=hora,
                            ticket_url=ticket_url,
                            ciclo=f"⚠️ parser falló · {cycle_name}",
                        ))
                    else:
                        # Ni ciclo ni estreno parseable → preservar título del card
                        result.append(Screening(
                            cine="Sala Lugones", title=cycle_name,
                            fecha=d.isoformat(), hora=hora,
                            ticket_url=ticket_url,
                            ciclo="Estreno",
                        ))
                except ValueError:
                    pass

        except Exception:
            result.append(Screening(
                cine="Sala Lugones", title=cycle_name,
                fecha="Sin fecha", hora="??", ticket_url=ticket_url,
            ))

    # Deduplicar
    seen: set[tuple] = set()
    deduped = []
    for s in result:
        key = (s.title, s.fecha, s.hora)
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


# ---------------------------------------------------------------------------
# Cacodelphia  (newsletter semanal por mail; la SPA queda de fallback)
# ---------------------------------------------------------------------------
#
# El cine manda cada miércoles/jueves un newsletter con la programación de la
# semana, y ese mail es mejor fuente que la web: trae título, ciclo,
# clasificación, horarios y el link exacto a la ficha, ya tabulado. La SPA en
# cambio obliga a descubrir links, esperar a que hidrate Vue y clickear tab por
# tab de fecha.
#
# Tres cosas que salieron de leer el histórico de la casilla, y que explican por
# qué el parser hace lo que hace:
#
#   · Se parsea el HTML, NO el text/plain. Las dos partes del mail se generan
#     por separado y divergen. El plano del 11/6/2026 se comió la función
#     "Lunes 15, 15:10hs" de LETRAS ROBADAS, y en la fe de erratas del 6/8/2026
#     corrigieron el HTML ("6 al 12 Agosto") dejando el plano con el mes viejo
#     ("6 al 12 Julio"). El HTML es lo que ve el lector.
#
#   · Las fechas se anclan en el header Date: del mail, nunca en el texto. Ese
#     mismo mail del 6/8 salió con asunto "30 de Julio al 5 de Agosto" y cuerpo
#     "6 al 12 Julio": ni el asunto ni el encabezado sirven. Las líneas de
#     horario traen sólo día de semana + número ("Jue 6"), y resolver ese número
#     contra la fecha de envío alcanza para fijar mes y año.
#
#   · Un mail más nuevo pisa TODAS las fechas que menciona. Las fe de erratas
#     repiten la semana entera ya corregida; deduplicando sólo por (título,
#     fecha, hora) sobrevivirían justamente las funciones que la corrección
#     venía a sacar.
#
#   · Los rangos no incluyen los lunes. El cine abre de jueves a miércoles y
#     cierra los lunes salvo feriado, así que un "Jue 6 a Mié 12" son seis días,
#     no siete. Cuando sí abren un lunes feriado el mail lo nombra aparte
#     ("Lunes 15, 15:10hs" el 15/6/2026, Güemes movido al lunes), y de ahí sale
#     la regla: un lunes entra sólo si el mail lo nombra explícitamente.


_CACO_MAIL_FROM = "cineartecacodelphia.com.ar"
_CACO_HOME = "https://cineartecacodelphia.com.ar/"

# Argentina no tiene DST desde 2009, así que un offset fijo nos ahorra depender
# de que el runner tenga tzdata.
_ART = timezone(timedelta(hours=-3))

_CACO_DIAS_ABBR = {"lun": 0, "mar": 1, "mie": 2, "jue": 3,
                   "vie": 4, "sab": 5, "dom": 6}

# IMAP quiere "06-Aug-2026" y strftime("%b") depende del locale del runner.
_MESES_IMAP = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_CACO_HORA_RE = re.compile(r"\b(\d{1,2}):(\d{2})")
_CACO_DIA_RE = re.compile(r"([A-Za-zÁÉÍÓÚÜáéíóúüñÑ]{3,10})\.?\s*(\d{1,2})\b")


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _caco_fecha(nombre: str, dia: int, enviado: date) -> Optional[date]:
    """Resuelve un "Jue 6" del mail a una fecha concreta.

    La ventana de 25 días es corta a propósito: en menos de 28 días un número de
    día aparece una sola vez, así que el número solo ya desambigua mes y año. El
    día de la semana se usa para confirmar, pero cuando no cierra gana el número
    — el cine se equivoca seguido con la abreviatura, y el número es lo que el
    lector usa para ir al cine.
    """
    wd = _CACO_DIAS_ABBR.get(_sin_acentos(nombre)[:3].lower())
    inicio = enviado - timedelta(days=2)
    cands = [d for d in (inicio + timedelta(days=i) for i in range(25))
             if d.day == dia]
    if not cands:
        return None
    if wd is not None:
        exactos = [d for d in cands if d.weekday() == wd]
        if exactos:
            return exactos[0]
    return cands[0]


def _caco_dias_nombrados(lineas: list[str], enviado: date) -> set[date]:
    """Fechas que el mail nombra explícitamente — día suelto o miembro de una
    lista, y también los extremos de un rango — a diferencia de las que quedan
    sólo implicadas por el interior de un rango.

    Se usa para decidir si un lunes está abierto: ver la nota del encabezado.
    """
    nombradas: set[date] = set()
    for linea in lineas:
        marcas = list(_CACO_HORA_RE.finditer(linea))
        if not marcas:
            continue
        for tramo in re.split(r"\s*-\s*", linea[:marcas[0].start()].rstrip(" ,")):
            for n, d in _CACO_DIA_RE.findall(tramo)[:2]:
                f = _caco_fecha(n, int(d), enviado)
                if f:
                    nombradas.add(f)
    return nombradas


def _caco_funciones(linea: str, enviado: date,
                    nombradas: Optional[set] = None) -> list[tuple[date, str]]:
    """Expande una línea de horarios a pares (fecha, "HH:MM").

    Formatos vistos, que además se combinan entre sí:
        Jue 6 a Mié 12, 18:00hs             rango
        Vie 7 - Sáb 8 - Mar 11, 18:40hs     lista
        Jue 2 - Sáb 4 a Mié 8, 19:00hs      lista con un rango adentro
        Miércoles 12, 19:00hs               día suelto, nombre completo
        Jue 6 a Mié 12, 16:20hs - 18:30hs   dos horarios para los mismos días

    El guión es ambiguo (separa días antes del primer horario y horarios
    después), así que cortamos en el primer horario en vez de partir por la
    coma, que a veces falta o viene despegada: "Vie 17 - Mié 22 , 16:40hs".
    """
    marcas = list(_CACO_HORA_RE.finditer(linea))
    if not marcas:
        return []
    horas = [f"{int(m.group(1)):02d}:{m.group(2)}"
             for m in marcas if int(m.group(1)) <= 23]
    if not horas:
        return []

    fechas: list[date] = []
    for tramo in re.split(r"\s*-\s*", linea[:marcas[0].start()].rstrip(" ,")):
        pares = _CACO_DIA_RE.findall(tramo)
        extremos = [f for f in (_caco_fecha(n, int(d), enviado)
                                for n, d in pares[:2]) if f]
        if not extremos:
            continue
        ini, fin = extremos[0], max(extremos[0], extremos[-1])
        # Un rango de más de dos semanas es basura del mail, no una temporada.
        d = ini
        while d <= fin and (d - ini).days <= 14:
            # Los lunes cierra, salvo feriado; y cuando abre, el mail lo nombra.
            if d.weekday() != 0 or nombradas is None or d in nombradas:
                fechas.append(d)
            d += timedelta(days=1)

    return [(f, h) for f in fechas for h in horas]


def _caco_ticket_url(a) -> str:
    """URL de la ficha desde el botón "Comprar Entradas".

    Mailjet envuelve el link en uno de tracking cuyo último segmento es la URL
    real en base64url. Si no desenvuelve a una URL del cine devolvemos el home,
    que es lo que hacía el scraper de la SPA.
    """
    href = (a.get("href") or "").strip() if a else ""
    if not href:
        return _CACO_HOME
    if _CACO_MAIL_FROM in href and "mjt.lu" not in href:
        return href
    seg = href.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    try:
        url = base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)).decode("utf-8")
    except Exception:
        return _CACO_HOME
    return url if url.startswith("http") and _CACO_MAIL_FROM in url else _CACO_HOME


def _caco_ciclo(celda) -> str:
    """Ciclo desde la banda roja que va arriba del poster ("CICLO LUIS ORTEGA").

    Sólo levantamos los ciclos de verdad: ESTRENO / REESTRENO / EXCLUSIVA /
    CLÁSICOS son etiquetas de marketing, no un programa, y ensuciarían el badge
    del sitio. Devolvemos el texto tal cual viene (en mayúsculas); run.py ya lo
    normaliza con _fix_caps.
    """
    bloque = celda.find_parent("table")
    if bloque is None:
        return ""
    for td in bloque.find_all("td"):
        if td.find("img"):
            break       # llegamos al poster: la banda del ciclo va antes
        txt = re.sub(r"\s+", " ", td.get_text(strip=True).replace("\xa0", " ")).strip()
        m = re.match(r"ciclo\s+(.+)$", txt, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _caco_parse_mail(html: str, enviado: date) -> list[Screening]:
    """Saca las funciones de un newsletter. `enviado` es la fecha local del mail.

    Cada película es un <h3> con el título, seguido de <p>s: la clasificación,
    "Horarios:", una o más líneas de horarios, y "Sinopsis:". Nos quedamos con
    lo que hay entre "Horarios:" y "Sinopsis:".
    """
    soup = BeautifulSoup(html, "html.parser")
    bloques: list[tuple] = []

    for h3 in soup.find_all("h3"):
        celda = h3.parent
        title, ciclo_titulo = _caco_titulo_y_ciclo(h3.get_text(strip=True))
        if celda is None or not title:
            continue

        ps = celda.find_all("p", recursive=False)
        i_hor = i_sin = None
        for i, p in enumerate(ps):
            txt = _sin_acentos(p.get_text(" ", strip=True)).lower()
            if i_hor is None and txt.startswith("horarios"):
                i_hor = i
            elif i_hor is not None and txt.startswith("sinopsis"):
                i_sin = i
                break
        if i_hor is None:
            continue

        lineas = [p.get_text(" ", strip=True).replace("\xa0", " ")
                  for p in ps[i_hor + 1: i_sin if i_sin is not None else len(ps)]]
        # La banda roja manda; el sufijo del título es el respaldo (los
        # festivales no siempre traen banda propia).
        bloques.append((title, _caco_ciclo(celda) or ciclo_titulo,
                        _caco_ticket_url(celda.find("a")), lineas))

    # Los lunes hay que resolverlos mirando el mail entero: el "Lunes 15" que
    # avisa que ese feriado abren puede estar en la ficha de otra película.
    nombradas = _caco_dias_nombrados([l for b in bloques for l in b[3]], enviado)

    out: list[Screening] = []
    for title, ciclo, ticket, lineas in bloques:
        for linea in lineas:
            for fecha, hora in _caco_funciones(linea, enviado, nombradas):
                out.append(Screening(
                    cine="Cacodelphia", title=title,
                    fecha=fecha.isoformat(), hora=hora,
                    ticket_url=ticket, ciclo=ciclo,
                ))
    return out


def _caco_mails(dias: int = 30) -> list[tuple[datetime, str]]:
    """Baja los newsletters de la casilla por IMAP, del más nuevo al más viejo.

    Sin credenciales devuelve [] y el caller cae al scraping de la SPA, así que
    el repo sigue andando para cualquiera que lo clone sin secrets.
    """
    user = os.environ.get("GMAIL_USER", "").strip()
    # Google muestra la contraseña de aplicación en cuatro grupos de cuatro y
    # es normal pegarla con los espacios; el servidor no los quiere.
    pwd = re.sub(r"\s+", "", os.environ.get("GMAIL_APP_PASSWORD", ""))
    if not (user and pwd):
        return []

    desde = date.today() - timedelta(days=dias)
    since = f"{desde.day:02d}-{_MESES_IMAP[desde.month - 1]}-{desde.year}"

    mails: list[tuple[datetime, str]] = []
    M = imaplib.IMAP4_SSL(os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com"))
    try:
        M.login(user, pwd)
        # readonly: es la casilla personal del dueño, no se la marcamos leída.
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "FROM", f'"{_CACO_MAIL_FROM}"', "SINCE", since)
        if typ != "OK":
            return []
        for uid in (data[0] or b"").split():
            typ, raw = M.fetch(uid, "(RFC822)")
            if typ != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1], policy=email.policy.default)
            parte = msg.get_body(preferencelist=("html",))
            if parte is None:
                continue
            try:
                enviado = email.utils.parsedate_to_datetime(msg["Date"])
            except Exception:
                continue
            if enviado.tzinfo is None:
                enviado = enviado.replace(tzinfo=timezone.utc)
            mails.append((enviado.astimezone(_ART), parte.get_content()))
    finally:
        try:
            M.logout()
        except Exception:
            pass

    # Por datetime, no por fecha: las fe de erratas salen el mismo día que el
    # mail que corrigen (6/8/2026: 11:04 y 11:14) y tienen que quedar primero.
    mails.sort(key=lambda t: t[0], reverse=True)
    return mails


# Festivales que el cine marca como sufijo del título ("Amora Mora - 8° FINCA").
# La sigla no le dice nada a nadie en la columna de ciclo, así que la mapeamos
# al nombre largo. Una sigla que no esté acá igual se separa del título.
_CACO_FESTIVALES = {
    "FINCA": "Festival Internacional de Cine Ambiental",
}

_CACO_FESTIVAL_RE = re.compile(r"\s*[-–—|:]\s*(\d{1,2})\s*[°º]\s*([^\-–—|:]{2,40})\s*$")

# Ciclos que el cine pega al final del título sin la palabra "Ciclo" y sin
# ordinal, así que no los agarra ninguno de los patrones de arriba: las cuatro
# funciones del DocBuenosAires entraron el 17/8/2026 como "Tu Rostro - Doc
# Bsas" con la columna de ciclo vacía. La clave es el sufijo normalizado (sin
# acentos ni espacios) porque el cine lo escribe distinto cada vez ("Doc Bsas",
# "DOC BSAS"), y el valor es cómo tiene que salir en la web.
#
# El nombre canónico va escrito EXACTAMENTE igual que en Lugones, que programa
# el mismo festival: si no coinciden carácter por carácter, la web los muestra
# como dos ciclos distintos y las funciones quedan separadas.
_CACO_CICLOS_PEGADOS = {
    "docbsas": "DocBuenosAires",
    "docbuenosaires": "DocBuenosAires",
    "docba": "DocBuenosAires",
}


def _caco_sufijo_conocido(sufijo: str) -> str:
    """Nombre canónico del ciclo si el sufijo es uno conocido, si no ''."""
    clave = re.sub(r"[^a-z0-9]+", "", _sin_acentos(sufijo).lower())
    return _CACO_CICLOS_PEGADOS.get(clave, "")


def _caco_titulo_y_ciclo(title: str) -> tuple[str, str]:
    """Separa del título el ciclo o festival que Cacodelphia le pega al final.

        "EL ÁNGEL - CICLO LUIS ORTEGA"  → ("EL ÁNGEL", "Luis Ortega")
        "Amora Mora - 8° FINCA"         → ("Amora Mora", "Festival Internacional…")
        "Tu Rostro - Doc Bsas"          → ("Tu Rostro", "DocBuenosAires")

    Dejar el sufijo adentro del título no sólo vacía la columna de ciclo:
    además rompe el enrichment. De las ocho películas del 8° FINCA que entraron
    el 7/8/2026 con el sufijo pegado, siete quedaron sin ficha de Letterboxd.
    """
    title = re.sub(r"\s+", " ", title).strip()

    m = re.search(r"\s*[-–—|:]\s*Ciclo\s+(.+)$", title, re.IGNORECASE)
    if m:
        return title[:m.start()].strip(), m.group(1).strip()

    m = re.match(r"^Ciclo\s+(.+?)\s*[-–—|:]\s*(.+)$", title, re.IGNORECASE)
    if m:
        return m.group(2).strip(), m.group(1).strip()

    m = _CACO_FESTIVAL_RE.search(title)
    if m:
        sigla = m.group(2).strip()
        # Un festival conocido manda su nombre canónico aunque venga con
        # ordinal ("40° DocBuenosAires"): así no se abre un ciclo nuevo por año.
        return (title[:m.start()].strip(),
                _caco_sufijo_conocido(sigla)
                or _CACO_FESTIVALES.get(sigla.upper(), f"{m.group(1)}° {sigla}"))

    # Sufijo pelado, sin "Ciclo" ni ordinal. Sólo se corta si es un ciclo que
    # conocemos: cortar cualquier cosa después de un guion se comería los
    # subtítulos que son parte del nombre de la película.
    m = re.search(r"\s*[-–—|:]\s*([^\-–—|:]{2,40})\s*$", title)
    if m:
        ciclo = _caco_sufijo_conocido(m.group(1))
        if ciclo:
            return title[:m.start()].strip(), ciclo

    return title, ""


def _caco_norm(title: str) -> str:
    """Título normalizado para cruzar mail contra web.

    Las dos fuentes escriben distinto la misma película ("LEVITICUS RITUAL DE
    SANGRE" vs "Leviticus: Ritual de sangre"), así que comparar los títulos
    crudos duplicaría en el sitio cada función que aparece en las dos.
    """
    return re.sub(r"[^a-z0-9]+", "", _sin_acentos(title).lower())


def _caco_clave(s: Screening) -> tuple:
    return (_caco_norm(s.title), s.fecha, s.hora)


def scrape_cacodelphia_mail(dias: int = 30) -> list[Screening]:
    """Funciones de los newsletters de los últimos `dias` días, sin la metadata
    que sólo está en la ficha del sitio."""
    hoy = date.today().isoformat()
    resultado: list[Screening] = []
    pisadas: set[str] = set()       # fechas ya cubiertas por un mail más nuevo
    vistas: set[tuple] = set()

    for enviado, html in _caco_mails(dias):
        try:
            funciones = _caco_parse_mail(html, enviado.date())
        except Exception as e:
            print(f"(mail del {enviado.date()} ilegible — {e})", end=" ", flush=True)
            continue
        for s in funciones:
            key = _caco_clave(s)
            if s.fecha in pisadas or s.fecha < hoy or key in vistas:
                continue
            vistas.add(key)
            resultado.append(s)
        pisadas |= {s.fecha for s in funciones}

    return resultado


async def scrape_cacodelphia(page: Page) -> list[Screening]:
    """Cartelera de Cacodelphia: el newsletter manda sobre su semana, la SPA
    aporta el resto.

    El mail es la fuente confiable de la semana en curso (ver la nota del
    encabezado), pero no es toda la cartelera: la web publica además funciones
    sueltas más adelante — ciclos que se repiten, preestrenos — que el mail de
    esta semana no menciona. Así que las dos fuentes se suman, con el mail
    pisando su propia semana para que la SPA no reviva una función que una fe
    de erratas sacó.

    Si no hay credenciales IMAP o la casilla no tiene mails recientes, la SPA
    queda de fuente única (que es como venía funcionando esto).
    """
    funciones = scrape_cacodelphia_mail()
    if not funciones:
        print("(sin mails; sólo SPA)", end=" ", flush=True)
        return await scrape_cacodelphia_spa(page)

    try:
        spa = await scrape_cacodelphia_spa(page)
    except Exception as e:
        # La SPA es la parte frágil y ya no es crítica: perdemos las funciones
        # de más adelante y los hints de metadata, pero la semana en curso sale
        # entera igual.
        print(f"(SPA falló, seguimos con el mail — {e})", end=" ", flush=True)
        return funciones

    # El mail no trae duración/director/año/país, pero la pasada por la SPA ya
    # los sacó de cada ficha (y del trailer, vía oEmbed). Los copiamos por
    # título en vez de volver a visitar las fichas: sirven de hint para que el
    # enrichment de Letterboxd no matchee la película equivocada.
    meta = {}
    for s in spa:
        k = _caco_norm(s.title)
        if k not in meta and (s.duration or s.director or s.year):
            meta[k] = s
    for s in funciones:
        m = meta.get(_caco_norm(s.title))
        if m:
            s.duration, s.director = m.duration, m.director
            s.year, s.country = m.year, m.country

    # Unión, sin dejar que el mail pise la semana entera: la web tiene
    # trasnoches y funciones sueltas que el newsletter no publicita (p.ej.
    # "Totalmente Poseidos", jue 6/8/2026 23:15). A diferencia de un mail viejo
    # —que una fe de erratas deja obsoleto— la SPA es el propio sistema de
    # venta del cine, así que no vale la pena descartarla para blindarse contra
    # una función cancelada: perder una función es peor que mostrar una de más.
    vistas = {_caco_clave(s) for s in funciones}
    # Índice por (fecha, hora) para el caso en que los títulos no coinciden
    # exacto: el <h3> del mail viene truncado con puntos suspensivos
    # ("TANGALANGA CONTRAATACA...") mientras la web trae el título entero.
    por_horario: dict[tuple, list] = {}
    for s in funciones:
        por_horario.setdefault((s.fecha, s.hora), []).append(_caco_norm(s.title))

    for s in spa:
        key = _caco_clave(s)
        if key in vistas:
            continue
        n = _caco_norm(s.title)
        # Misma fecha y hora, y un título es prefijo del otro → es la misma
        # función. Sin esto se duplica en el sitio.
        if any(n.startswith(m) or m.startswith(n)
               for m in por_horario.get((s.fecha, s.hora), [])):
            continue
        vistas.add(key)
        por_horario.setdefault((s.fecha, s.hora), []).append(n)
        funciones.append(s)
    return funciones


# ---------------------------------------------------------------------------
# Cacodelphia — fallback: cineartecacodelphia.com.ar (Vue SPA)
# ---------------------------------------------------------------------------

_YT_ID_RE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_TRAILER_NOISE = ("trailer", "tráiler", "teaser", "oficial", "official", "hd", "4k", "min", "subt")


def _looks_like_person(s: str) -> bool:
    """Heurística para descartar basura del título del trailer: 1-4 palabras,
    alfabéticas, mayúscula inicial, sin términos de marketing."""
    if not s or len(s) > 50:
        return False
    if any(w in s.lower() for w in _TRAILER_NOISE):
        return False
    words = s.split()
    if not (1 <= len(words) <= 4):
        return False
    ok = sum(1 for w in words
             if w[:1].isupper() and re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ'.\-]+", w))
    return ok >= max(1, len(words) - 1)


def _cacodelphia_trailer_meta(html: str) -> dict:
    """Extrae {director, year, country} del título del trailer de YouTube
    embebido en la ficha de Cacodelphia, vía oEmbed.

    La ficha NO expone director/año en texto, pero el trailer suele titularse
    "Título (trailer) · Director · AÑO · País · NN min". Es best-effort: si el
    formato no matchea (no hay separador "·" o no hay año plausible), devuelve
    {} y no agrega hints — preferimos no inventar a meter un dato erróneo.
    """
    m = _YT_ID_RE.search(html or "")
    if not m:
        return {}
    watch = f"https://www.youtube.com/watch?v={m.group(1)}"
    oembed = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(watch, safe="") + "&format=json"
    try:
        req = urllib.request.Request(oembed, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}
    title_txt = data.get("title", "") or ""
    if "·" not in title_txt:
        return {}
    parts = [p.strip() for p in title_txt.split("·") if p.strip()]
    this_year = date.today().year
    out: dict = {}
    for i, p in enumerate(parts):
        if not re.fullmatch(r"(?:19|20)\d{2}", p):
            continue
        yr = int(p)
        if not (1920 <= yr <= this_year + 1):
            continue
        out["year"] = yr
        # Director = campo inmediatamente anterior (no el título en índice 0).
        if i >= 2 and _looks_like_person(parts[i - 1]):
            out["director"] = parts[i - 1]
        # País = campo siguiente, si parece un país (texto sin dígitos, corto).
        if i + 1 < len(parts):
            nxt = parts[i + 1]
            if nxt and not re.search(r"\d", nxt) and "min" not in nxt.lower() and len(nxt) <= 40:
                out["country"] = nxt
        break
    return out


async def scrape_cacodelphia_spa(page: Page) -> list[Screening]:
    """
    Página principal → links /pelicula/86/HASH → por cada película, click en
    cada tab de fecha y extraer horarios. La ficha no trae director/año en
    texto, así que los inferimos del título del trailer de YouTube (oEmbed)
    para que el enrichment valide bien y no matchee la película equivocada.

    Quedó de fallback: sólo corre si no hay newsletters en la casilla.
    """
    await page.goto("https://cineartecacodelphia.com.ar/", wait_until="networkidle")
    await page.wait_for_timeout(3000)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    NON_TITLES = {"estreno", "cast", "subt", "2d", "3d", "subtitulado", "doblado"}
    seen_hrefs: set[str] = set()
    movie_links: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=re.compile(r"^/pelicula/")):
        href = a["href"]
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        p_el = a.find("p", class_=lambda c: c and "truncate" in c.split())
        # El título suele traer el ciclo o el festival pegado ("El Jockey -
        # Ciclo Luis Ortega", "Amora Mora - 8° FINCA"): lo separamos.
        title, ciclo = _caco_titulo_y_ciclo(p_el.get_text(strip=True) if p_el else "")
        if title and len(title) > 1 and title.lower() not in NON_TITLES:
            movie_links.append((href, title, ciclo))

    result: list[Screening] = []
    seen_screenings: set[tuple] = set()

    for href, title, ciclo in movie_links:
        url = f"https://cineartecacodelphia.com.ar{href}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Duración: la página muestra "NN MIN" justo debajo del título
        full_text = await page.evaluate("document.body.innerText")
        dur_match = re.search(r"\b(\d{1,3})\s*MIN\b", full_text)
        film_duration: Optional[int] = int(dur_match.group(1)) if dur_match else None

        # Director/año/país desde el trailer (la ficha no los trae en texto).
        detail_html = await page.content()
        tmeta = _cacodelphia_trailer_meta(detail_html)
        film_director = tmeta.get("director", "")
        film_year = tmeta.get("year")
        film_country = tmeta.get("country", "")

        date_tabs = await page.query_selector_all("div.date")
        if not date_tabs:
            continue

        for tab in date_tabs:
            tab_text = (await tab.inner_text()).strip()
            lines = [l.strip() for l in tab_text.split("\n") if l.strip()]
            fecha_str = lines[-1] if lines else ""
            fecha = parse_date_ddmm(fecha_str)

            if not fecha:
                continue
            try:
                if date.fromisoformat(fecha) < date.today():
                    continue
            except ValueError:
                pass

            try:
                await tab.click()
                await page.wait_for_timeout(600)
            except Exception:
                pass

            page_text = await page.evaluate("document.body.innerText")
            func_idx = page_text.lower().find("funciones para")
            segment = page_text[func_idx:func_idx + 400] if func_idx != -1 else page_text[:400]

            for t in re.findall(r"\b(\d{1,2}:\d{2})\b", segment):
                hora = f"{int(t.split(':')[0]):02d}:{t.split(':')[1]}"
                key = (title, fecha, hora)
                if key not in seen_screenings:
                    seen_screenings.add(key)
                    result.append(Screening(
                        cine="Cacodelphia", title=title,
                        fecha=fecha, hora=hora,
                        # `url` es la ficha de esta película, que es donde se
                        # compra; mandar al home obliga a buscarla de nuevo.
                        ticket_url=url,
                        ciclo=ciclo,
                        duration=film_duration,
                        director=film_director,
                        year=film_year,
                        country=film_country,
                    ))

    return result


# ---------------------------------------------------------------------------
# Cine Lorca  (Wix — la cartelera la suben como imagen, así que se carga
# manualmente desde data/lorca_manual.json)
# ---------------------------------------------------------------------------

import json
from pathlib import Path

LORCA_MANUAL_PATH = Path(__file__).parent / "data" / "lorca_manual.json"


LORCA_IMDB_BASE = (
    "https://www.imdb.com/showtimes/cinema/AR/ci1036356/AR/C1134/"
)


def _parse_lorca_imdb_text(text: str) -> list[dict]:
    """
    Parsea el innerText de la página de showtimes IMDb para Cine Lorca.

    Cada película aparece así (saltos de línea reales):

        El diablo viste a la moda 2
        20261h 59mPG-13
        6.7
         (42 k)
        Calificar
        Marcar como visto
        Estándar:
        4:00 PM
        8:20 PM

    Devuelve [{title, year, duration, times: ["HH:MM",...]}, ...].
    """
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[dict] = []
    # Año + duración en una sola palabra: "20261h 59mPG-13" o "2026 1h 59m R"
    meta_re = re.compile(r"^(\d{4})(\d+)h(\d+)m", re.IGNORECASE)
    time_re = re.compile(r"^(\d{1,2}):(\d{2})\s+(AM|PM)$", re.IGNORECASE)

    i = 0
    while i < len(lines):
        compact = lines[i].replace(" ", "") if lines[i] else ""
        mm = meta_re.match(compact)
        if not mm:
            i += 1
            continue
        year = int(mm.group(1))
        duration = int(mm.group(2)) * 60 + int(mm.group(3))
        # La línea anterior no-vacía es el título
        title = ""
        k = i - 1
        while k >= 0 and not lines[k]:
            k -= 1
        if k >= 0:
            title = lines[k]
        # Recolectar horarios hasta el próximo meta o fin
        times: list[str] = []
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            if not ln:
                j += 1
                continue
            if ln.startswith("Datos de horarios") or ln.startswith("Más para explorar"):
                break
            if meta_re.match(ln.replace(" ", "")):
                break
            tm = time_re.match(ln)
            if tm:
                h = int(tm.group(1))
                m = int(tm.group(2))
                ampm = tm.group(3).upper()
                if ampm == "PM" and h < 12:
                    h += 12
                elif ampm == "AM" and h == 12:
                    h = 0
                times.append(f"{h:02d}:{m:02d}")
            j += 1
        if title and times:
            out.append({"title": title, "year": year, "duration": duration, "times": times})
        i = j
    return out


async def _scrape_imdb_cinema(
    page: "Page",
    imdb_id: str,
    cine_name: str,
    ticket_url: str,
    semanas: int = 2,
    postal: str = "C1134",
) -> list[Screening]:
    """
    Scrapea IMDb showtimes para un cine genérico. imdb_id es el ID 'ciNNNNNN'.
    Cine_name se usa como discriminador para detectar el redirect/bot-block:
    la página debe contener el nombre.

    Si imdb_id está vacío, retorna inmediatamente lista vacía para que el
    caller caiga al fallback de La Nación.
    """
    if not imdb_id:
        return []
    today = date.today()
    end = today + timedelta(days=7 * semanas)
    result: list[Screening] = []
    seen: set[tuple] = set()

    base = f"https://www.imdb.com/showtimes/cinema/AR/{imdb_id}/AR/{postal}/"
    d = today
    while d <= end:
        url = f"{base}{d.isoformat()}/"
        text = ""
        for attempt in range(2):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3500 if attempt == 0 else 6000)
                text = await page.evaluate("document.body.innerText")
            except Exception:
                text = ""
            if cine_name in text:
                break

        if cine_name not in text:
            d += timedelta(days=1)
            continue

        for film in _parse_lorca_imdb_text(text):
            for hora in film["times"]:
                key = (film["title"], d.isoformat(), hora)
                if key in seen:
                    continue
                seen.add(key)
                result.append(Screening(
                    cine=cine_name,
                    title=film["title"],
                    fecha=d.isoformat(),
                    hora=hora,
                    ticket_url=ticket_url,
                    year=film.get("year"),
                    duration=film.get("duration"),
                ))
        d += timedelta(days=1)

    return result


# ───── Lanación: cartelera por sala ────────────────────────────────────
#
# IMDb dejó de servir la programación de Lorca (y de varias salas más).
# La Nación sí tiene una página por sala que lista las películas en cartel
# y desde el detail de cada peli sacamos los horarios en ESA sala.
# Solo trae el día actual — el cron diario lo va actualizando.

LANACION_BASE = "https://www.lanacion.com.ar"

def _parse_lanacion_film_funciones(text: str) -> dict[str, list[str]]:
    """
    Parsea el bloque 'FUNCIONES DE ...' del detail de una peli en lanacion
    y devuelve { sala_name: ["HH:MM", "HH:MM", ...], ... } juntando los
    horarios de TODOS los formatos (subtitulada, castellano, 3D, etc.)
    para esa sala.

    Estructura del texto:
        FUNCIONES DE
        EL DRAMA
        Lorca
        COMPRAR ENTRADAS
        subtitulada: 22:10
        Showcase Cinemas Norcenter
        COMPRAR ENTRADAS
        subtitulada: 16:50, 19:25, 21:50
        OTRAS PELÍCULAS
    """
    out: dict[str, list[str]] = {}
    start = text.find("FUNCIONES DE")
    end = text.find("OTRAS PELÍCULAS")
    if start < 0:
        return out
    block = text[start: end if end > start else len(text)]
    lines = [ln.strip() for ln in block.split("\n")]

    # La sala se identifica por POSICIÓN: cualquier línea que no sea
    # "Formato: HH:MM, HH:MM" abre una sala nueva y los horarios que siguen son
    # suyos. Antes el ancla era la línea "COMPRAR ENTRADAS" que iba debajo de
    # cada sala; La Nación la sacó (junto con "OTRAS PELÍCULAS") y sin ancla
    # current_sala nunca se seteaba: los siete cines comerciales quedaban en
    # cero. Sin ancla fija, un rediseño del botón ya no rompe el parseo.
    formato_re = re.compile(
        r"^[^:]{1,40}:\s*((?:\d{1,2}:\d{2})(?:\s*,\s*\d{1,2}:\d{2})*)\s*$")
    current_sala = ""
    for ln in lines:
        if not ln or ln == "COMPRAR ENTRADAS":
            continue
        m = formato_re.match(ln)
        if not m:
            current_sala = ln
            continue
        if not current_sala:
            continue
        for t in re.findall(r"\d{1,2}:\d{2}", m.group(1)):
            hh, mm = t.split(":")
            out.setdefault(current_sala, []).append(f"{int(hh):02d}:{mm}")
    # Dedup + sort
    for k in out:
        out[k] = sorted(set(out[k]))
    return out


def _scrape_lanacion_sala(slug: str, lanacion_name: str, cine_name: str,
                          ticket_url: str) -> list[Screening]:
    """
    Scrapea /cartelera-de-cine/sala/<slug> en lanacion.com.ar:
    1) Obtiene la lista de pelis en esa sala.
    2) Para cada peli, parsea su detail page y extrae los horarios de la
       sala (matcheando por `lanacion_name`).
    3) Devuelve Screenings con fecha=hoy (lanacion sólo muestra el día actual).
    """
    today = date.today().isoformat()
    sala_url = f"{LANACION_BASE}/cartelera-de-cine/sala/{slug}"
    try:
        sala_soup = fetch_html(sala_url)
    except Exception as e:
        print(f"[lanacion {slug}: no carga — {e}]", end=" ")
        return []

    film_paths: list[tuple[str, str]] = []  # (path, title-from-listing)
    seen: set[str] = set()
    for a in sala_soup.find_all("a", href=re.compile(r"^/cartelera-de-cine/pelicula/")):
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        # El título de la listing es sólo un fallback — el bueno sale del h1 del
        # detalle. Desde ~julio de 2026 La Nación envuelve nada más que el
        # poster en el <a>, así que get_text() viene vacío: exigirlo dejaba la
        # listing en cero y con ella los siete cines comerciales.
        title = a.get_text(strip=True)
        if not title:
            img = a.find("img")
            title = re.sub(r"^P[óo]ster de\s+", "",
                           (img.get("alt") or "") if img else "").strip()
        film_paths.append((href, title))

    # Diagnóstico: si la listing no trae links de película, el sitio cambió de
    # estructura (o pasó a render por JS) y hay que rehacer el parser. Sin esto
    # el 0 es mudo y no se distingue de "hoy no hay funciones".
    if not film_paths:
        print(f"[lanacion {slug}: 0 links de película en la listing]", end=" ")

    result: list[Screening] = []
    for path, list_title in film_paths:
        try:
            det = fetch_html(LANACION_BASE + path)
        except Exception:
            continue
        text = det.get_text("\n", strip=True)
        # Título prolijo desde el h1 (la listing puede tener case raro)
        h1 = det.find("h1")
        title = (h1.get_text(strip=True) if h1 else list_title).strip()
        # Algunos h1 vienen en MAYÚSCULAS; preferimos sentence-case
        if title and title.isupper():
            title = title.capitalize()

        funciones = _parse_lanacion_film_funciones(text)
        horarios = funciones.get(lanacion_name, [])
        if not horarios:
            continue
        for hora in horarios:
            result.append(Screening(
                cine=cine_name,
                title=title,
                fecha=today,
                hora=hora,
                ticket_url=ticket_url,
            ))
    return result


def scrape_lorca_lanacion() -> list[Screening]:
    """Cine Lorca via lanacion (fallback cuando IMDb no responde)."""
    return _scrape_lanacion_sala(
        slug="lorca-sa110",
        lanacion_name="Lorca",
        cine_name="Cine Lorca",
        ticket_url="https://cinelorca.wixsite.com/cine-lorca",
    )


# ───── IMDb + La Nación combinados ────────────────────────────────────
#
# IMDb servía la semana completa y La Nación sólo el día actual, así que la
# estrategia era IMDb primero con La Nación de fallback.
#
# Desde el 23/7/2026 IMDb dejó de servir showtimes: /showtimes/cinema/… devuelve
# 202 con el body vacío para todos los cines. Como el fallback también estaba
# roto, los siete comerciales pasaron diez días publicando la data preservada
# de la corrida del 23 (Cinemark Caballito llegó a mostrar UN título).
#
# IMDB_HABILITADO apaga esa primera pasada: son hasta 21 días × 4 cines de
# navegación con esperas de 3,5-6 s cada una — más de diez minutos de job para
# recibir páginas vacías. La Nación queda como fuente única. Se pierde la
# ventana a futuro (La Nación publica sólo hoy); si IMDb vuelve, alcanza con
# poner esto en True.
IMDB_HABILITADO = False

# Cine → (imdb_id, cine_display_name, ticket_url, lanacion_slug, lanacion_name)
# (imdb_id, cine_display_name, ticket_url, lanacion_slug, lanacion_name, imdb_postal)
IMDB_CINEMAS = [
    ("ci1036356", "Cine Lorca",             "https://cinelorca.wixsite.com/cine-lorca",
     "lorca-sa110",                           "Lorca",                       "C1134"),
    # Cinemark CABA (3 sucursales)
    ("ci1036344", "Cinemark Caballito",     "https://www.cinemark.com.ar/",
     "cinemark-caballito-sa130",              "Cinemark Caballito",          "C1134"),
    ("ci1036343", "Cinemark Palermo",       "https://www.cinemark.com.ar/",
     "cinemark-palermo-sa223",                "Cinemark Palermo",            "C1134"),
    ("",          "Cinemark Puerto Madero", "https://www.cinemark.com.ar/",
     "cinemark-puerto-madero-sa102",          "Cinemark Puerto Madero",      "C1134"),
    # Hoyts CABA (2 sucursales)
    ("ci1036354", "Hoyts Abasto",           "https://www.hoyts.com.ar/",
     "hoyts-abasto-de-buenos-aires-sa95",     "Hoyts Abasto de Buenos Aires","C1134"),
    ("",          "Hoyts Dot",              "https://www.hoyts.com.ar/",
     "hoyts-dot-sa520",                       "Hoyts Dot",                   "C1134"),
    # Cinépolis CABA (2 sucursales)
    ("ci1033339", "Cinépolis Houssay",      "https://www.cinepolis.com.ar/",
     "cinepolis-plaza-houssay-sa1225",        "Cinépolis Plaza Houssay",     "C1134"),
    ("ci1036368", "Cinépolis Recoleta",     "https://www.cinepolis.com.ar/",
     "cinepolis-recoleta-sa400",              "Cinépolis Recoleta",          "C1428"),
    # Showcase CABA (1 sucursal — Belgrano)
    ("",          "Showcase Belgrano",      "https://www.todoshowcase.com/",
     "showcase-cinemas-belgrano-sa170",       "Showcase Cinemas Belgrano",   "C1134"),
]


async def scrape_imdb_then_lanacion(page: Page, semanas: int = 2) -> list[Screening]:
    """
    Por cada cine en IMDB_CINEMAS:
      1) Intenta IMDb (multi-día, hasta `semanas` semanas)
      2) Si no devuelve nada, fallback a La Nación (solo hoy)
    Devuelve la unión deduplicada.
    """
    all_screenings: list[Screening] = []
    seen: set[tuple] = set()

    # IMDb se scrapea día por día, así que el costo crece linealmente con la
    # ventana. Lorca y los comerciales no publican funciones más allá de ~2-3
    # semanas, así que acotamos acá para no disparar el runtime del job (la
    # ventana larga de 2 meses solo tiene sentido para los cines de repertorio).
    imdb_semanas = min(semanas, 3)

    for imdb_id, cine_name, ticket_url, lan_slug, lan_name, postal in IMDB_CINEMAS:
        # Las salas del grupo Cinemark Hoyts van por su propia API, que trae
        # varios días y ficha técnica. Acá quedan Lorca, Cinépolis y Showcase.
        if cine_name in CINEMARKHOYTS_CINES:
            continue
        print(f"  · {cine_name}...", end=" ", flush=True)
        ss: list[Screening] = []
        # 1) IMDb (apagado: ver IMDB_HABILITADO)
        if IMDB_HABILITADO:
            try:
                ss = await _scrape_imdb_cinema(page, imdb_id, cine_name, ticket_url, imdb_semanas, postal=postal)
            except Exception as e:
                print(f"IMDb error — {e};", end=" ")
                ss = []
        # 2) Fallback La Nación si IMDb no devolvió nada (skipea si no hay slug)
        if not ss and lan_slug:
            try:
                ss = _scrape_lanacion_sala(lan_slug, lan_name, cine_name, ticket_url)
                print(f"fallback lanacion: {len(ss)} func.")
            except Exception as e:
                print(f"lanacion error — {e}")
                continue
        elif ss:
            print(f"{len(ss)} funciones (IMDb)")
        else:
            print("0 funciones")

        for s in ss:
            k = (s.cine, s.title, s.fecha, s.hora)
            if k in seen:
                continue
            seen.add(k)
            all_screenings.append(s)

    return all_screenings


# Cines comerciales de CABA scrapeados desde lanacion. Cada entry:
#   (sala_slug, lanacion_name, cine_display_name, ticket_url)
# Agregá más sucursales acá con la misma forma — el scraper las toma todas.
LANACION_COMMERCIAL_CINEMAS = [
    ("cinemark-caballito-sa130",            "Cinemark Caballito",         "Cinemark Caballito",     "https://www.cinemark.com.ar/"),
    ("cinemark-palermo-sa223",              "Cinemark Palermo",           "Cinemark Palermo",       "https://www.cinemark.com.ar/"),
    ("cinemark-puerto-madero-sa102",        "Cinemark Puerto Madero",     "Cinemark Puerto Madero", "https://www.cinemark.com.ar/"),
    ("hoyts-abasto-de-buenos-aires-sa95",   "Hoyts Abasto de Buenos Aires","Hoyts Abasto",          "https://www.hoyts.com.ar/"),
    ("hoyts-dot-sa520",                     "Hoyts Dot",                  "Hoyts Dot",              "https://www.hoyts.com.ar/"),
    ("cinepolis-plaza-houssay-sa1225",      "Cinépolis Plaza Houssay",    "Cinépolis Houssay",      "https://www.cinepolis.com.ar/"),
    ("showcase-cinemas-belgrano-sa170",     "Showcase Cinemas Belgrano",  "Showcase Belgrano",      "https://www.todoshowcase.com/"),
]


def scrape_commercial_lanacion() -> list[Screening]:
    """Itera la lista de salas comerciales en lanacion y dedup."""
    all_screenings: list[Screening] = []
    seen: set[tuple] = set()
    for slug, lan_name, cine_name, ticket_url in LANACION_COMMERCIAL_CINEMAS:
        print(f"  · {cine_name}...", end=" ", flush=True)
        try:
            ss = _scrape_lanacion_sala(slug, lan_name, cine_name, ticket_url)
        except Exception as e:
            print(f"error — {e}")
            continue
        added = 0
        for s in ss:
            k = (s.cine, s.title, s.fecha, s.hora)
            if k in seen:
                continue
            seen.add(k)
            all_screenings.append(s)
            added += 1
        print(f"{added} funciones")
    return all_screenings


# ───── Multiplex ──────────────────────────────────────────────────────
#
# La home sirve la grilla ENTERA en el HTML: ~1000 funciones (todas las salas ×
# todos los días × todas las pelis) como <span class="horario-btn"> con la data
# en atributos. El selector de fecha y el de complejo son filtros client-side
# que sólo agregan/sacan la clase `visible` — por eso elegir una fecha no
# dispara ningún request. Un solo GET trae toda la cartelera; no hace falta
# browser ni pedir la ficha de cada película.
#
# Se parsean los atributos y no el texto visible: son ISO-ish, sin ambigüedad
# de idioma, y sobreviven a cambios de CSS.
MULTIPLEX_BASE = "https://multiplex.com.ar"

# complejo_id → nombre de sala en sitedigo. Los IDs salen del <select id="complejo">
# de cualquier ficha (/peliculas/<slug>/).
#
# Las cuatro de AMBA. San Juan (190) queda afuera: es otra provincia, a 1.100 km.
# Para sumarla alcanza con descomentar — el resto del scraper la toma sola.
#
# El nombre de cada sala es el que usa la cadena, que es lo que la gente ve en
# la marquesina y en la web de Multiplex. "Canning" es el barrio (partido de
# Ezeiza); si algún día conviene, se cambia acá y sólo acá.
MULTIPLEX_COMPLEJOS = {
    "182": "Multiplex Belgrano",      # CABA
    "184": "Multiplex Lavalle",       # CABA
    "180": "Multiplex Canning",       # Canning, Ezeiza (GBA)
    "187": "Multiplex Pilar",         # Pilar (GBA)
    # "190": "Multiplex San Juan",    # provincia de San Juan
}

MULTIPLEX_TICKET_URL = f"{MULTIPLEX_BASE}/"


def _multiplex_fecha(dia: str) -> Optional[str]:
    """'08.13.2026' → '2026-08-13'.

    OJO: el orden es MM.DD.YYYY (americano), no DD.MM. Verificado contra el
    carrusel del sitio, que rotula ese mismo valor como "Jueves Ago 13".
    """
    m = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*", dia or "")
    if not m:
        return None
    mes, day, anio = (int(x) for x in m.groups())
    try:
        return date(anio, mes, day).isoformat()
    except ValueError:
        return None


def _multiplex_card_info(card) -> tuple[str, str]:
    """(título, slug) de una tarjeta de película de la home.

    Las tarjetas las genera un loop de Elementor, así que el markup del título
    puede cambiar sin aviso: se prueban varias vías antes de rendirse.
    """
    slug = ""
    a = card.find("a", href=re.compile(r"/peliculas/[^/]+/?"))
    if a and a.get("href"):
        m = re.search(r"/peliculas/([^/?#]+)", a["href"])
        if m:
            slug = m.group(1)

    candidatos = []
    if a:
        candidatos.append(a.get_text(strip=True))
    for h in card.find_all(["h1", "h2", "h3", "h4", "h5"], limit=3):
        candidatos.append(h.get_text(strip=True))
    for el in card.select('[class*="titulo"], [class*="title"]')[:3]:
        candidatos.append(el.get_text(strip=True))
    img = card.find("img")
    if img:
        candidatos.append(re.sub(r"^(P[óo]ster|Afiche)\s+de\s+", "",
                                 img.get("alt") or "", flags=re.I).strip())

    for c in candidatos:
        # Descarta los CTA del propio botón ("Ver horarios", "Comprar entradas")
        if c and len(c) > 1 and not re.match(r"^(ver|comprar|m[áa]s)\b", c, re.I):
            return c.strip(), slug

    # Último recurso: el slug, que al menos es identificable a ojo en la web.
    return (slug.replace("-", " ").title() if slug else ""), slug


def scrape_multiplex(semanas: int = 2) -> list[Screening]:
    """Cartelera de Multiplex desde el HTML de la home (un solo GET)."""
    hoy = date.today()
    cutoff = (hoy + timedelta(weeks=semanas)).isoformat()
    hoy_str = hoy.isoformat()

    try:
        soup = fetch_html(MULTIPLEX_BASE + "/")
    except Exception as e:
        print(f"[multiplex: no carga — {e}]", end=" ")
        return []

    cards = soup.select("div.funcion-item")
    if not cards:
        # Diagnóstico explícito: sin esto un rediseño del sitio devuelve 0 y se
        # confunde con "hoy no hay funciones" (pasó con lanacion en julio).
        print("[multiplex: 0 tarjetas .funcion-item — cambió el markup]", end=" ")
        return []

    result: list[Screening] = []
    seen: set[tuple] = set()
    sin_titulo = 0
    desfasadas = 0

    for card in cards:
        titulo, slug = _multiplex_card_info(card)
        if not titulo:
            sin_titulo += 1
            continue
        ticket = f"{MULTIPLEX_BASE}/peliculas/{slug}/" if slug else MULTIPLEX_TICKET_URL

        for span in card.select("[data-hora][data-complejo][data-dia]"):
            cine = MULTIPLEX_COMPLEJOS.get(str(span.get("data-complejo", "")).strip())
            if not cine:
                continue                      # sucursal fuera de scope
            fecha = _multiplex_fecha(span.get("data-dia", ""))
            if not fecha or fecha < hoy_str or fecha > cutoff:
                continue
            hora = str(span.get("data-hora", "")).strip()
            if not re.fullmatch(r"\d{1,2}:\d{2}", hora):
                continue
            hora = f"{int(hora.split(':')[0]):02d}:{hora.split(':')[1]}"

            # data-dia-real existe por si una trasnoche se agrupa bajo el día
            # anterior. Hoy coincide siempre con data-dia; si algún día deja de
            # coincidir lo queremos saber antes de que la función aparezca en el
            # día equivocado.
            real = _multiplex_fecha(span.get("data-dia-real", "") or "")
            if real and real != fecha:
                desfasadas += 1

            k = (cine, titulo, fecha, hora)
            if k in seen:
                continue                      # misma función en 2D y COMFORT PLUS
            seen.add(k)
            result.append(Screening(
                cine=cine,
                title=titulo,
                fecha=fecha,
                hora=hora,
                ticket_url=ticket,
            ))

    if sin_titulo:
        print(f"[multiplex: {sin_titulo} tarjetas sin título]", end=" ")
    if desfasadas:
        print(f"[multiplex: {desfasadas} con data-dia-real ≠ data-dia]", end=" ")
    return result


def scrape_lorca() -> list[Screening]:
    """
    Fallback manual cuando IMDb falla. Lee data/lorca_manual.json con shape:
      {"period_start": "...", "period_end": "...",
       "films": [{"title": "...", "times": ["HH:MM", ...]}, ...]}
    """
    if not LORCA_MANUAL_PATH.exists():
        print("[Lorca] no existe data/lorca_manual.json", flush=True)
        return []
    try:
        data = json.loads(LORCA_MANUAL_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Lorca] lorca_manual.json ilegible: {e}", flush=True)
        return []

    try:
        start = date.fromisoformat(data["period_start"])
        end = date.fromisoformat(data["period_end"])
    except (KeyError, ValueError) as e:
        print(f"[Lorca] período inválido en lorca_manual.json: {e}", flush=True)
        return []

    today = date.today()
    # El rango se vence solo cuando cambia la programación semanal. Sin este
    # aviso el scrape devolvía 0 funciones en silencio y la sala desaparecía
    # de la web sin que nada lo señalara.
    if end < today:
        print(f"[Lorca] lorca_manual VENCIDO (period_end={end}, hoy={today}) — "
              f"actualizá la programación de la semana", flush=True)
        return []
    result: list[Screening] = []
    d = max(start, today)
    while d <= end:
        for film in data.get("films", []):
            title = film.get("title", "").strip()
            if not title:
                continue
            for t in film.get("times", []):
                m = re.match(r"^(\d{1,2}):(\d{2})$", t.strip())
                if not m:
                    continue
                hora = f"{int(m.group(1)):02d}:{m.group(2)}"
                result.append(Screening(
                    cine="Cine Lorca", title=title,
                    fecha=d.isoformat(), hora=hora,
                    ticket_url="https://cinelorca.wixsite.com/cine-lorca",
                ))
        d += timedelta(days=1)

    return result


# ---------------------------------------------------------------------------
# Cine Gaumont  (cinegaumont.ar — pelis con API JSON pública /films/ID/tree)
# ---------------------------------------------------------------------------

def scrape_gaumont(semanas: int = 2) -> list[Screening]:
    """
    1. Lista filmids desde cinegaumont.ar/Default (links /pelicula.aspx?filmid=N)
    2. Para cada filmid, parsea metadata de la página de detalle.
    3. Llama a la API JSON oficial cinegaumont.com.ar/films/ID/tree para
       obtener fechas y horarios.
    """
    BASE_WEB = "https://www.cinegaumont.ar"
    BASE_API = "https://www.cinegaumont.com.ar"

    try:
        home = fetch_html(f"{BASE_WEB}/Default")
    except Exception:
        return []

    filmids: list[str] = []
    seen: set[str] = set()
    for a in home.find_all("a", href=re.compile(r"pelicula\.aspx\?filmid=\d+")):
        m = re.search(r"filmid=(\d+)", a["href"])
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            filmids.append(m.group(1))

    # Mapeo filmid → nombre del ciclo. La home tiene varios headings que
    # agrupan films, todos como <div class="col-12">:
    #   - "Ciclo X"            → ciclo = "X"           (ej. "Ciclo Funciones Unicas")
    #   - "Estrenos"           → ciclo = "Estreno"
    #   - "Películas en cartel"→ ciclo = "En cartel"
    # Los films del grupo son los siblings hasta el próximo heading.
    HEADING_TO_CICLO = {
        "estrenos": "Estreno",
        "películas en cartel": "En cartel",
        "peliculas en cartel": "En cartel",
    }
    filmid_to_ciclo: dict[str, str] = {}
    ciclo_re = re.compile(r"^Ciclo\s+(.+)$", re.IGNORECASE)

    def _heading_to_ciclo(text: str) -> str:
        text = text.strip()
        m = ciclo_re.match(text)
        if m:
            return m.group(1).strip()
        return HEADING_TO_CICLO.get(text.lower(), "")

    def _is_heading(text: str) -> bool:
        return bool(_heading_to_ciclo(text))

    for div in home.find_all("div", class_="col-12"):
        ciclo_name = _heading_to_ciclo(div.get_text(strip=True))
        if not ciclo_name:
            continue
        nxt = div
        while True:
            nxt = nxt.find_next_sibling()
            if nxt is None:
                break
            if nxt.name == "div" and "col-12" in (nxt.get("class") or []):
                if _is_heading(nxt.get_text(strip=True)):
                    break
                continue
            for a in nxt.find_all("a", href=re.compile(r"filmid=")) if hasattr(nxt, "find_all") else []:
                mm = re.search(r"filmid=(\d+)", a["href"])
                if mm and mm.group(1) not in filmid_to_ciclo:
                    filmid_to_ciclo[mm.group(1)] = ciclo_name

    result: list[Screening] = []
    today = date.today()
    end = today + timedelta(weeks=semanas)

    for fid in filmids:
        # Metadata de la peli (título, director, país, duración)
        meta: dict = {}
        try:
            soup = fetch_html(f"{BASE_WEB}/pelicula.aspx?filmid={fid}")
            h1 = soup.find(["h1", "h2"])
            title = h1.get_text(strip=True) if h1 else ""
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            m = re.search(r"Dirección\s*:\s*([^\n.]+?)(?:\s+Elenco|\s+Origen|\s+Género|\s*©|\s*$)", text)
            director = m.group(1).strip() if m else ""
            m = re.search(r"Orig?en\s*:\s*([^\n.]+?)\s+Género", text)
            country = m.group(1).strip() if m else ""
            m = re.search(r"(\d{2,3})\s+minutos?\b", text)
            duration = int(m.group(1)) if m else None
            meta = {"title": title, "director": director, "country": country, "duration": duration}
        except Exception:
            continue
        if not meta.get("title"):
            continue

        # Horarios via API JSON
        try:
            req = urllib.request.Request(
                f"{BASE_API}/films/{fid}/tree",
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
            import json as _json
            data = _json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            continue

        for fecha_str, venues in (data.get("days") or {}).items():
            try:
                d = date.fromisoformat(fecha_str)
            except ValueError:
                continue
            if d < today or d > end:
                continue
            for venue in venues:
                for fmt in venue.get("formats", []):
                    for perf in fmt.get("performances", []):
                        st = perf.get("showTime") or ""
                        m = re.match(r"(\d{1,2}):(\d{2})", st)
                        if not m:
                            continue
                        hora = f"{int(m.group(1)):02d}:{m.group(2)}"
                        result.append(Screening(
                            cine="Cine Gaumont",
                            title=meta["title"],
                            fecha=d.isoformat(),
                            hora=hora,
                            ticket_url=f"{BASE_WEB}/pelicula.aspx?filmid={fid}",
                            ciclo=filmid_to_ciclo.get(fid, ""),
                            director=meta.get("director", ""),
                            country=meta.get("country", ""),
                            duration=meta.get("duration"),
                        ))
    return result


# ---------------------------------------------------------------------------
# CCK  (palaciolibertad.gob.ar — events con JSON-LD que detalla la programación)
# ---------------------------------------------------------------------------

CCK_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# La descripción de cada ciclo del CCK trae la ficha de las películas, en dos
# formatos distintos, y hasta ahora no se usaba ninguno: la cartelera publicaba
# las funciones del CCK sin director.
#
#   1. Bloque "Programación", el más completo:
#        Hijo mayor "Cecilia Kang. Argentina, Francia, 2025. 118'. Drama."
#   2. Enumeración del ciclo, con el año y a veces la co-dirección:
#        Se proyectan diez títulos: El hombre robado (2007), …,
#        Sycorax (Matías Piñeiro y Lois Patiño, 2021), …
#   3. Y para las retrospectivas de un solo autor, el copete lo nombra:
#        "un recorrido por la obra de Matías Piñeiro"
#      Eso cubre los programas dobles ("Rosalinda + Sycorax"), que no matchean
#      contra ninguna de las dos listas.
_CCK_NOMBRE = r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’.\-]*){0,3}"
_CCK_AUTOR_RE = re.compile(
    rf"(?:(?:la\s+)?obra\s+de|[Rr]etrospectiva\s+(?:de\s+)?|[Hh]omenaje\s+a)\s+({_CCK_NOMBRE})")
# Va anclado al título y NO exige comillas: el sitio las escribe, pero se
# pierden al desescapar el JSON-LD, así que el texto que ve el scraper es
# «Hijo mayor Cecilia Kang. Argentina, Francia, 2025. 118'.» pelado.
_CCK_FICHA_RE = re.compile(
    r"\s*[\"“]?\s*([^\".]{3,60})\.\s*(?:([^\".]{0,70}?),\s*)?"
    r"((?:19|20)\d{2})\.\s*(\d{2,3})\s*[’\'′]")
_CCK_LISTA_RE = re.compile(r"[Ss]e\s+proyectan[^:]{0,40}:\s*(.+?)\.\s")


def _cck_norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower().translate(_MALBA_ACCENTS)).strip()


def _cck_fichas(texto: str) -> dict:
    """{título normalizado: {director, country, year, duration}} desde el
    bloque "Programación" y desde la enumeración del ciclo."""
    out: dict = {}

    ml = _CCK_LISTA_RE.search(texto)
    if ml:
        # Cortamos por comas que NO estén dentro de un paréntesis, para no
        # partir "Sycorax (Matías Piñeiro y Lois Patiño, 2021)" al medio.
        for item in re.split(r",\s*(?![^()]*\))", ml.group(1)):
            mm = re.match(r"\s*(.+?)\s*\(([^)]*)\)\s*$", item)
            if not mm:
                continue
            datos: dict = {}
            my = re.search(r"(?:19|20)\d{2}", mm.group(2))
            if my:
                datos["year"] = int(my.group(0))
            resto = re.sub(r",?\s*(?:19|20)\d{2}\s*$", "", mm.group(2)).strip()
            if resto:
                datos["director"] = resto
            if datos:
                out[_cck_norm(mm.group(1))] = datos
    return out


def _cck_titulo_re(titulo: str) -> "re.Pattern":
    """El mismo título con los espacios sueltos.

    La agenda y el bloque "Programación" no escriben igual el mismo título:
    arriba «16:30 h: Borges/Santiago: Variaciones sobre un guion» y abajo
    «Borges / Santiago: Variaciones sobre un guion Alejo Moguillansky. 2008.
    76'.». Buscando el string literal no matcheaba ninguna de las dos y la
    función salía a la cartelera sin director, sin año y sin duración.
    """
    tokens = re.findall(r"\w+|[^\w\s]", titulo)
    return re.compile(r"\s*".join(re.escape(t) for t in tokens), re.IGNORECASE)


def _cck_ficha_programacion(texto: str, titulo: str) -> dict:
    """Ficha del bloque "Programación" para un título puntual.

    Se busca desde el marcador "Programación" en adelante porque el título
    también aparece más arriba, en la agenda ("19 h: Hijo mayor"), donde no
    tiene ficha detrás.
    """
    if not re.search(r"\w", titulo):     # un título sin letras matchearía cualquier cosa
        return {}
    desde = texto.find("Programación")
    for tm in _cck_titulo_re(titulo).finditer(texto, desde if desde >= 0 else 0):
        m = _CCK_FICHA_RE.match(texto, tm.end())
        if m:
            return {"director": m.group(1).strip(),
                    # El país es opcional: unas fichas van "Director. País,
                    # Año. NN'." y otras directo "Director. Año. NN'."
                    "country": (m.group(2) or "").strip(),
                    "year": int(m.group(3)),
                    "duration": int(m.group(4))}
    return {}


_CCK_SALA_RE = re.compile(
    r"^(?:Auditorio|Sala|Microcine|Cine)\s+[^:]{1,30}:\s*", re.IGNORECASE)


def _json_ld_loads(raw: Optional[str]):
    """json.loads tolerante para los bloques JSON-LD de los sitios.

    El CCK escribe las duraciones como «118\\'» dentro de la description: `\\'`
    es un escape válido en JavaScript pero NO en JSON, así que json.loads
    explota y el evento entero se descartaba en silencio. Desde julio de 2026
    los dos ciclos de palaciolibertad.gob.ar caían por esto y el cine quedaba
    en cero. Reintentamos sacando ese escape (el lookbehind evita romper un
    backslash escapado de verdad).
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(re.sub(r"(?<!\\)\\'", "'", raw))
    except Exception:
        return None


def scrape_cck(semanas: int = 2) -> list[Screening]:
    """
    1. Lista events desde palaciolibertad.gob.ar/cine/
    2. Cada event tiene JSON-LD con "description" en HTML que detalla
       fecha + hora + título de cada función dentro del ciclo.
    
    Manejo especial para eventos con múltiples películas por horario:
    Ejemplo: "19 h: El castillo  Nancy"
    Se parsea como DOS películas separadas.

    El 14/8/2026 palaciolibertad.gob.ar empezó a devolverle a la IP del runner
    el challenge de Cloudflare (200 + "Just a moment…", el sitio entero: /cine/,
    los events, el sitemap y el wp-json). Como el HTML del challenge no tiene
    links /events/, el scraper no fallaba: devolvía [] y el cine desaparecía de
    la cartelera sin un solo error en el log. Por eso ahora las dos bajadas van
    por fetch_html_cf, que cae al proxy residencial —el mismo que ya usa el
    Borges— cuando aparece el challenge.
    """
    BASE = "https://palaciolibertad.gob.ar"
    soup = fetch_html_cf(f"{BASE}/cine/", "CCK: la agenda de cine")
    if soup is None:
        return []

    event_urls: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"/events/")):
        u = a["href"]
        if not u.startswith("http"):
            u = BASE + u
        if u not in seen:
            seen.add(u)
            event_urls.append(u)

    result: list[Screening] = []
    today = date.today()
    end = today + timedelta(weeks=semanas)

    import json as _json
    import html as _html

    for event_url in event_urls:
        ev_soup = fetch_html_cf(event_url, f"CCK: {event_url}")
        if ev_soup is None:
            continue
        h1 = ev_soup.find("h1")
        cycle_name = h1.get_text(strip=True) if h1 else ""

        # JSON-LD trae startDate/endDate y description con HTML.
        description_html = ""
        start_iso = end_iso = ""
        for sc in ev_soup.find_all("script", type="application/ld+json"):
            d = _json_ld_loads(sc.string)
            if not isinstance(d, dict) or d.get("@type") != "Event":
                continue
            description_html = _html.unescape(d.get("description") or "")
            start_iso = (d.get("startDate") or "")[:10]
            end_iso = (d.get("endDate") or "")[:10]
            break
        if not description_html:
            continue

        try:
            ev_start = date.fromisoformat(start_iso) if start_iso else None
            ev_end = date.fromisoformat(end_iso) if end_iso else ev_start
        except ValueError:
            ev_start = ev_end = None

        # Si el evento entero queda fuera de la ventana, skip
        if ev_end and ev_end < today:
            continue
        if ev_start and ev_start > end:
            continue

        # Mes/año por defecto para fechas que no los explicitan en el texto
        default_month = ev_start.month if ev_start else today.month
        default_year = ev_start.year if ev_start else today.year

        desc_soup = BeautifulSoup(description_html, "html.parser")
        # Patrones soportados dentro de la descripción:
        #   "Sábado 2 de mayo  19 h: TITLE"            (día + mes explícito)
        #   "Viernes 22  17 h: TITLE  19:30 h: TITLE"  (día sin "de mes")
        #   "15 h: TITLE"                              (solo hora — usa ev_start)
        # date_re intenta capturar día con o sin "de mes"
        date_re = re.compile(
            r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+"
            r"(\d{1,2})(?:\s+de\s+(\w+)(?:\s+(?:de\s+)?(\d{4}))?)?",
            re.IGNORECASE,
        )
        # El \d* después de la "h" cubre los typos del CCK ("18:30 h1:" en la
        # retrospectiva de Piñeiro). Sin eso el horario no se reconocía como
        # slot nuevo y la película se pegaba al título de la función anterior.
        slot_re = re.compile(
            r"(\d{1,2})(?::(\d{2}))?\s*h(?:s|oras)?\d*\s*[:.\-–]\s*"
            r"(.+?)"
            r"(?=\s+\d{1,2}(?::\d{2})?\s*h(?:s|oras)?\d*\s*[:.\-–]|\Z)",
            re.IGNORECASE | re.DOTALL,
        )

        # Procesamos la descripción entera y agrupamos por header de fecha.
        # Si nunca aparece un header de fecha, los slots se asignan a ev_start.
        full_text = desc_soup.get_text(" ", strip=True)
        full_text = re.sub(r"\s+", " ", full_text)

        # Fichas de este ciclo: la enumeración de títulos y, para las
        # retrospectivas de un solo autor, el director del ciclo entero.
        fichas_ciclo = _cck_fichas(full_text)
        ma = _CCK_AUTOR_RE.search(full_text)
        autor_ciclo = ma.group(1).strip() if ma else ""

        # Encontrar headers de fecha + sus rangos en el texto
        date_anchors: list[tuple[int, int, date]] = []  # (start, end, fecha resuelta)
        for dm in date_re.finditer(full_text):
            day_num = int(dm.group(1))
            month_name = (dm.group(2) or "").lower()
            year = int(dm.group(3)) if dm.group(3) else default_year
            month = CCK_MONTHS.get(month_name, default_month)
            try:
                d_resolved = date(year, month, day_num)
            except ValueError:
                continue
            # Si la fecha quedó en el pasado lejano y el evento es a futuro, +1 año
            if d_resolved < today - timedelta(days=30) and not month_name:
                try:
                    d_resolved = date(year + 1, month, day_num)
                except ValueError:
                    continue
            date_anchors.append((dm.start(), dm.end(), d_resolved))

        # Construir secciones (start_idx, end_idx, fecha). Sin anchors, una
        # sola sección que cubre todo el texto y asocia a ev_start.
        sections: list[tuple[int, int, date]] = []
        if date_anchors:
            for i, (a_start, a_end, a_date) in enumerate(date_anchors):
                next_start = date_anchors[i + 1][0] if i + 1 < len(date_anchors) else len(full_text)
                sections.append((a_end, next_start, a_date))
        elif ev_start:
            sections.append((0, len(full_text), ev_start))

        for sec_start, sec_end, sec_date in sections:
            if sec_date < today or sec_date > end:
                continue
            chunk = full_text[sec_start:sec_end]
            for sm in slot_re.finditer(chunk):
                hour = int(sm.group(1))
                minute = int(sm.group(2)) if sm.group(2) else 0
                raw_title_chunk = sm.group(3).strip(" -–:.,;\n")
                # Cortar en frases típicas de pie de página del CCK
                raw_title_chunk = re.split(
                    r"\s+(?:Las\s+proyecciones|Programaci[óo]n\b|Funciones\b)",
                    raw_title_chunk, maxsplit=1, flags=re.IGNORECASE,
                )[0]
                # A veces el CCK repite la sala después de la hora ("16:30 h -
                # Auditorio 511: La princesa de Francia"): el guion cuenta como
                # separador de slot y la sala termina pegada al título.
                raw_title_chunk = _CCK_SALA_RE.sub("", raw_title_chunk, count=1)
                titles = re.split(r"\s{2,}|\n", raw_title_chunk)
                for raw_title in titles:
                    raw_title = raw_title.strip(" -–:.,;")
                    if not raw_title or len(raw_title) < 2:
                        continue
                    hora = f"{hour:02d}:{minute:02d}"
                    # Ficha: primero la del bloque "Programación" (trae país y
                    # duración), después la enumeración, y de última el autor
                    # del ciclo — que es lo que cubre los programas dobles.
                    ficha = _cck_ficha_programacion(full_text, raw_title)
                    if not ficha:
                        ficha = dict(fichas_ciclo.get(_cck_norm(raw_title), {}))
                    if not ficha.get("director") and autor_ciclo:
                        ficha["director"] = autor_ciclo
                    result.append(Screening(
                        cine="CCK",
                        title=raw_title,
                        fecha=sec_date.isoformat(),
                        hora=hora,
                        ticket_url=event_url,
                        ciclo=cycle_name,
                        director=ficha.get("director", ""),
                        country=ficha.get("country", ""),
                        year=ficha.get("year"),
                        duration=ficha.get("duration"),
                    ))

    # Deduplicar (cycle pages a veces repiten fechas)
    seen_keys: set[tuple] = set()
    deduped: list[Screening] = []
    for s in result:
        key = (s.title.lower(), s.fecha, s.hora)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(s)
    return deduped


# ---------------------------------------------------------------------------
# Cine Cosmos UBA  (cosmos.uba.ar — la home ya trae la cartelera completa)
# ---------------------------------------------------------------------------
# Cada película de la home es una card autocontenida, y ahí está todo:
#
#   <div class="card">
#     <a href="/pelicula?idPelicula=408"><img alt="Letras robadas"></a>
#     <div class="card-body">
#       <h4 class="card-title">Letras robadas</h4>
#       <p class="direccion">Dirección: John Carney</p>
#       <p class="lightText">Irlanda / 98m</p>
#     </div>
#     <div class="card-footer"><p>Vi Sá Do Lu Ma Mi | 15:00</p></div>
#   </div>
#
# El footer es el que manda: o trae los días con sus horarios, o dice
# "Próximamente" — y ahí la película todavía NO tiene funciones, así que no va
# a la cartelera. Ese es el caso de todo el ciclo de cine francés de agosto de
# 2026, que se publicó con la ficha completa semanas antes de tener horarios.
#
# Antes esto salía de una página de detalle por película
# (`/?c=main&a=Detalle&idPelicula=NNN`). Esa ruta ya no existe: el sitio
# contesta la home entera para CUALQUIER id. Como el scraper aplanaba ese HTML
# y buscaba bloques "días | horarios" en todo el texto, cada película se
# quedaba con los horarios de todas — 843 funciones fantasma en la cartelera
# del 15/8/2026, las "Próximamente" incluidas, con el país lleno de restos del
# aplanado ("ximamente Trailer Letras robadas Irlanda") y el director de la
# primera peli repetido en el resto. Leyendo la card no hace falta ninguna
# heurística para saber de quién es cada horario: está en su propio nodo.
#
# Lo único que se pierde es el año (la ficha de la card no lo trae): lo
# completa el enriquecimiento por Letterboxd/TMDB, que además lo traía bien
# cuando el detalle lo daba mal. El detalle nuevo (/pelicula?idPelicula=NNN)
# sólo se usa como ticket_url.
# ---------------------------------------------------------------------------

COSMOS_DAY_ABBREV = {
    "lu": 0, "lun": 0,
    "ma": 1, "mar": 1,
    "mi": 2, "mie": 2, "mié": 2, "mier": 2,
    "ju": 3, "jue": 3,
    "vi": 4, "vie": 4,
    "sa": 5, "sab": 5, "sá": 5, "sáb": 5,
    "do": 6, "dom": 6,
}

# "Vi Sá Do Lu Ma Mi | 15:00" y también "Sá Do Lu Ma Mi | 18:50 - 20:50": los
# días valen para todos los horarios del bloque. El grupo de horarios captura
# sólo dígitos/":"/separadores, así que corta solo si aparece otro bloque.
_COSMOS_SLOT_RE = re.compile(
    r"((?:(?:Lu|Ma|Mi|Mié|Mier|Ju|Vi|S[áa]|Do)\b\s*-?\s*)+)\|\s*([\d:\s\-–—,]+)",
    re.IGNORECASE,
)


def _cosmos_slots(footer_text: str) -> list[tuple[set[int], str]]:
    """(días de la semana, hora) del footer de una card.

    Devuelve [] cuando el footer dice "Próximamente" — que es justamente cómo
    se distingue una película anunciada de una programada.
    """
    slots: list[tuple[set[int], str]] = []
    for m in _COSMOS_SLOT_RE.finditer(footer_text or ""):
        weekdays = {COSMOS_DAY_ABBREV[t]
                    for t in re.findall(r"[a-záéí]+", m.group(1).lower())
                    if t in COSMOS_DAY_ABBREV}
        if not weekdays:
            continue
        for hh, mm in re.findall(r"(\d{1,2}):(\d{2})", m.group(2)):
            slots.append((weekdays, f"{int(hh):02d}:{mm}"))
    return slots


def scrape_cosmos(semanas: int = 2) -> list[Screening]:
    """Scrapea la cartelera de cosmos.uba.ar desde las cards de la home."""
    # El sitio se mudó: www.cinecosmos.uba.ar redirige 301 a cosmos.uba.ar.
    # Se apunta al dominio nuevo para que los ticket_url no salgan redirigidos.
    BASE = "https://cosmos.uba.ar"
    try:
        home = fetch_html(f"{BASE}/")
    except Exception:
        return []

    today = date.today()
    # La cartelera de Cosmos va Jueves → Miércoles y se actualiza cada Jueves.
    # No tiene sentido expandir más allá del próximo Miércoles porque después
    # el sitio publica una programación nueva. weekday(): Mon=0 ... Wed=2 ... Sun=6
    days_to_wed = (2 - today.weekday()) % 7
    end = today + timedelta(days=days_to_wed)

    cards = home.select("div.card")
    result: list[Screening] = []
    proximamente = 0

    for card in cards:
        titulo_el = card.select_one(".card-title")
        title = re.sub(r"\s+", " ", titulo_el.get_text(" ", strip=True)) if titulo_el else ""
        # El afiche del ciclo también entra como card, con el título en "." y la
        # ficha vacía. Sin dos letras seguidas no es un título de película.
        if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2}", title):
            continue

        footer = card.select_one(".card-footer")
        slots = _cosmos_slots(footer.get_text(" ", strip=True) if footer else "")
        if not slots:
            proximamente += 1
            continue

        link = card.find("a", href=re.compile(r"idPelicula=\d+"))
        m = re.search(r"idPelicula=(\d+)", link["href"]) if link else None
        ticket_url = f"{BASE}/pelicula?idPelicula={m.group(1)}" if m else f"{BASE}/"

        director = ""
        dir_el = card.select_one("p.direccion")
        if dir_el:
            director = re.sub(r"^\s*Direcci[óo]n\s*:\s*", "",
                              re.sub(r"\s+", " ", dir_el.get_text(" ", strip=True))).strip(" .,-")

        # "Irlanda / 98m" — el país es lo que va antes de la duración.
        country, duration = "", None
        ficha_el = card.select_one("p.lightText")
        if ficha_el:
            ficha = re.sub(r"\s+", " ", ficha_el.get_text(" ", strip=True))
            md = re.search(r"(\d{2,3})\s*m\b", ficha)
            if md:
                duration = int(md.group(1))
            # El punto NO se saca: "EE.UU." lo lleva adentro y al final.
            country = re.sub(r"\s*/?\s*\d{2,3}\s*m\b.*$", "", ficha).strip(" /,-")

        d = today
        while d <= end:
            for weekdays, hora in slots:
                if d.weekday() in weekdays:
                    result.append(Screening(
                        cine="Cine Cosmos",
                        title=title,
                        fecha=d.isoformat(),
                        hora=hora,
                        ticket_url=ticket_url,
                        director=director,
                        country=country,
                        duration=duration,
                    ))
            d += timedelta(days=1)

    # Dedup por si el sitio vuelve a renderizar la misma card dos veces (el
    # template anterior repetía el bloque de horarios y duplicaba funciones).
    seen: set[tuple] = set()
    deduped: list[Screening] = []
    for s in result:
        key = (s.title, s.fecha, s.hora)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)

    # Diagnóstico explícito: sin esto un rediseño del sitio devuelve 0 (o datos
    # raros) y se confunde con "esta semana no hay funciones".
    if cards and not deduped:
        print(f"[cosmos: {len(cards)} cards en la home pero 0 funciones — "
              f"revisar el markup]", end=" ")
    elif proximamente:
        print(f"[cosmos: {proximamente} anunciadas sin horario]", end=" ")
    return deduped


# ---------------------------------------------------------------------------
# Lumiton  (lumiton.ar/agenda-presencial/) — devuelve funciones de los 3
# venues de la fundación Lumiton: Cine York, Centro Cultural Munro y Lumiton.
# ---------------------------------------------------------------------------

# Slug en data-locations → nombre visible que usamos como `cine`
LUMITON_VENUES: dict[str, str] = {
    "cine-york": "Cine York",
    "centro-cultural-munro": "Centro Cultural Munro",
    "lumiton": "Lumiton",
}


def fetch_lumiton_evento_meta(url: str) -> dict:
    """
    Extrae director / país / duración / año / título original desde una página
    /evento/ de Lumiton. La ficha tiene esta estructura:
      <div class="mb-4 uppercase">
        <b>Dirección</b> NAME(s)
        <b>Título Original</b> ORIGINAL  (opcional)
        <div class="text-sm">COUNTRY. NN min. YYYY.</div>
      </div>
    """
    if not url:
        return {}
    try:
        soup = fetch_html(url)
    except Exception:
        return {}

    out: dict = {}

    # Director: text after <b>Dirección</b>, until next <br>/<b>/<div>
    for b in soup.find_all("b"):
        label = b.get_text(strip=True)
        if label.lower() == "dirección":
            # Take next sibling text
            sib = b.next_sibling
            if sib and isinstance(sib, str):
                out["director"] = re.sub(r"\s+", " ", sib).strip()
        elif label.lower() == "título original":
            sib = b.next_sibling
            if sib and isinstance(sib, str):
                out["original_title"] = re.sub(r"\s+", " ", sib).strip()

    # Country / duration / year: live in <div class="text-sm">
    # Format variations:
    #   "Argentina. 103 min. 2004."
    #   "EE.UU.. 101 min. 1939."
    #   "Argentina, España. 87 min. Ficción. 2023."   ← género extra entre min y year
    #   "Singapur, Taiwán. 126'. 2024."               ← apóstrofe en vez de "min"
    text_sm = soup.select_one("div.text-sm")
    if text_sm:
        line = re.sub(r"\s+", " ", text_sm.get_text(" ", strip=True))

        # Duración: el primer "NN min" o "NN'" en la línea
        md = re.search(r"\b(\d{1,3})\s*(?:min\b|['′])", line)
        if md:
            out["duration"] = int(md.group(1))

        # Año: ÚLTIMO 19XX/20XX en la línea (suele venir al final)
        years = re.findall(r"\b(19\d{2}|20\d{2})\b", line)
        if years:
            out["year"] = int(years[-1])

        # País: lo que está antes de "NN min" (o "NN'")
        if md:
            country_chunk = line[: md.start()].rstrip()
            country_chunk = country_chunk.rstrip(".").strip()
            if country_chunk:
                out["country"] = country_chunk

    return out

ARTHAUS_AGENDA_URL = "https://arthaus.ar/agenda/"

# Día de semana opcional + día(s) + "de" mes + hora. Sirve para las líneas de
# función que aparecen en el cuerpo de cada detalle, p.ej:
#   "jueves 18 de junio, 20 H"   /   "jueves 25 de junio 20 H"
_ARTHAUS_MONTHS = "|".join(MESES_ES.keys())
_ARTHAUS_DATE_RE = re.compile(
    rf"(?:(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|sábados|sabados|domingos)\s+)?"
    rf"((?:\d{{1,2}}(?:\s*y\s*\d{{1,2}})*))\s+de\s+({_ARTHAUS_MONTHS}),?\s+"
    # La hora va con dos puntos o con punto: la web escribe "19.30 H".
    rf"(\d{{1,2}})(?:[.:](\d{{2}}))?\s*(?:h|hs|horas?)\b",
    re.IGNORECASE,
)

ARTHAUS_CINE_URL = "https://arthaus.ar/cine/"
# Bloque de película en arthaus.ar/cine/. El ancla es la línea "Dir. NOMBRE":
#
#     LO QUE TRAJO LA TORMENTA          ← título (la línea anterior)
#     Dir. Miguel de Zuviría
#     Sábados 8 y 29 de agosto, 20 H    ← puede traer varias fechas
#     + Q&A
#     <sinopsis> (duración: 120’)
#     entradas                          ← link a la boletería
#
_ARTHAUS_DIR_RE = re.compile(r"^dir\.\s*(.+)$", re.IGNORECASE)
_ARTHAUS_DUR_RE = re.compile(r"duraci[óo]n\s*:\s*(\d{1,3})", re.IGNORECASE)
_ARTHAUS_LINK_RE = re.compile(r"^(?:entradas|inscripci[óo]n\b.*)$", re.IGNORECASE)
# "¡estreno!" viene como prefijo del título o en su propia línea.
_ARTHAUS_ESTRENO_RE = re.compile(r"^\s*[¡!]*\s*estreno\s*!*\s*", re.IGNORECASE)


def _arthaus_clean_title(raw: str) -> str:
    """Quita el prefijo "CINE ARTHAUS." que llevan los títulos de cine."""
    t = re.sub(r"^\s*cine\s+arthaus\s*[\.\:\-–—]*\s*", "", raw or "", flags=re.IGNORECASE).strip()
    return t or (raw or "").strip()


def _parse_arthaus_detail(title_raw: str, body: str, url: str,
                          today: date, cutoff: date) -> list[Screening]:
    """Parsea el texto plano de una página de detalle de arthaus.ar.

    Sólo devuelve funciones si la CATEGORÍA del evento incluye "cine".
    Extrae director y año desde la descripción ("... Dir. NOMBRE, AÑO ...") y
    las fechas de función desde las líneas del cuerpo; si no hay, cae al bloque
    estructurado FECHA / HORA del sidebar.
    """
    flat = re.sub(r"[ \t]+", " ", body or "")
    low = flat.lower()

    # 1) Filtro por categoría: el sidebar lista "CATEGORÍA  Cine  cine-actual".
    mcat = re.search(r"categor[ií]a\s*(.{0,80})", low, re.DOTALL)
    cat_blob = mcat.group(1) if mcat else ""
    is_cine = ("cine" in cat_blob) or bool(re.search(r"\bcine[\s-]?actual\b", low))
    if not is_cine:
        return []

    title = _arthaus_clean_title(title_raw)
    if not title:
        return []

    # 2) Director + año desde la descripción: "Dir. Manuel Besedovsky, 2024".
    director = ""
    year: Optional[int] = None
    md = re.search(r"dir\.\s*(?:por\s+)?([^,\n.]+?)\s*,?\s*\b((?:19|20)\d{2})\b", flat, re.IGNORECASE)
    if md:
        director = md.group(1).strip()
        year = int(md.group(2))
    else:
        md = re.search(r"dir\.\s*(?:por\s+)?([^,\n.]+)", flat, re.IGNORECASE)
        if md:
            director = md.group(1).strip()
        my = re.search(r"\b((?:19|20)\d{2})\b", flat)
        if my:
            year = int(my.group(1))

    # 3) Fechas de función. Primero las líneas explícitas del cuerpo.
    funcs: set[tuple[str, str]] = set()  # (YYYY-MM-DD, HH:MM)
    for m in _ARTHAUS_DATE_RE.finditer(low):
        month = MESES_ES.get(m.group(2).lower())
        if not month:
            continue
        hour = int(m.group(3))
        minute = int(m.group(4)) if m.group(4) else 0
        hora = f"{hour:02d}:{minute:02d}"
        for day in (int(x) for x in re.findall(r"\d{1,2}", m.group(1))):
            for y in (today.year, today.year + 1):
                try:
                    d = date(y, month, day)
                except ValueError:
                    continue
                if today <= d <= cutoff:
                    funcs.add((d.isoformat(), hora))
                    break

    # 4) Fallback: bloque estructurado del sidebar — "FECHA 18 - 25 06 26" y
    #    "HORA 20:00 - 20:00". Los números antes de MM YY son los días de función.
    if not funcs:
        mh = re.search(r"hora\s*(\d{1,2}:\d{2})", low)
        mf = re.search(r"fecha\s*([\d\s\-–—]+)", low)
        if mh and mf:
            hora = mh.group(1)
            if len(hora) == 4:
                hora = "0" + hora
            nums = [int(x) for x in re.findall(r"\d{1,2}", mf.group(1))]
            if len(nums) >= 3:
                month = nums[-2]
                yy = nums[-1]
                yr = yy + 2000 if yy < 100 else yy
                for day in nums[:-2]:
                    try:
                        d = date(yr, month, day)
                    except ValueError:
                        continue
                    if today <= d <= cutoff:
                        funcs.add((d.isoformat(), hora))

    return [
        Screening(
            cine="Arthaus",
            title=title,
            fecha=f,
            hora=h,
            ticket_url=url or ARTHAUS_AGENDA_URL,
            director=director,
            year=year,
        )
        for (f, h) in sorted(funcs)
    ]


def scrape_arthaus(semanas: int = 3) -> list[Screening]:
    """Scrapea arthaus.ar/cine/ — la programación de cine del mes.

    Antes leía /agenda/ buscando tarjetas con "VER DETALLE". Esa agenda dejó de
    listar cine (hoy no devuelve ni un link /agenda/<slug>/), así que la sala
    venía con 3 funciones sueltas mientras la web publicaba diez películas.
    /cine/ las tiene todas, en HTML servido: sin playwright y sin abrir un
    detalle por película.

    Se recorre sección por sección (las de Elementor) porque ahí está la única
    señal confiable de a qué ciclo pertenece cada película. Hay dos formas:

      · Carátula de ciclo — una sección con el nombre del ciclo y la línea
        "Ciclo de cine", sin ninguna ficha. El ciclo se aplica a la sección
        SIGUIENTE, que es la que trae sus películas ("Quizás, quizás, quizás"
        y sus tres films).
      · Ciclo de una sola película — el nombre del ciclo y la película comparten
        sección, y se reconocen porque quedan DOS encabezados antes del "Dir."
        en vez de uno ("Cine Fri: la película gratuita del mes" → "1982").

    Antes esto se resolvía por texto plano y el nombre del ciclo terminaba
    publicado como si fuera una película.
    """
    today = date.today()
    # Arthaus reparte cada película en 2 funciones separadas por semanas
    # (p.ej. sábados 8 y 29), así que la ventana va más ancha que la global.
    cutoff = today + timedelta(weeks=max(semanas, 6))

    try:
        soup = fetch_html(ARTHAUS_CINE_URL)
    except Exception as e:
        print(f"[arthaus: no carga — {e}]", end=" ", flush=True)
        return []

    result: list[Screening] = []
    ciclo_pendiente = ""

    for sec in soup.find_all("section", class_="elementor-top-section"):
        hrefs = [a["href"] for a in sec.find_all("a", href=True)
                 if _ARTHAUS_LINK_RE.match(a.get_text(" ", strip=True))]
        lineas = [l for l in _inner_text(sec).split("\n") if l]
        if not lineas:
            continue

        fichas = [i for i, l in enumerate(lineas) if _ARTHAUS_DIR_RE.match(l)]
        if not fichas:
            if any(l.lower() == "ciclo de cine" for l in lineas):
                ciclo_pendiente = lineas[0].strip()
            continue

        # El ciclo pendiente vale para esta sección y se consume acá.
        ciclo_seccion, ciclo_pendiente = ciclo_pendiente, ""

        link_k = 0
        fin_anterior = -1
        for n, i in enumerate(fichas):
            director = _ARTHAUS_DIR_RE.match(lineas[i]).group(1).strip(" .,")
            title = _ARTHAUS_ESTRENO_RE.sub("", lineas[i - 1]).strip() if i else ""
            # Dos encabezados antes de la ficha → el primero es el ciclo. Se
            # saltea el "¡estreno!", que también viene en su propia línea y si
            # no se filtra termina publicado como si fuera el nombre del ciclo.
            ciclo = ciclo_seccion
            for j in range(fin_anterior + 1, i - 1):
                cand = _ARTHAUS_ESTRENO_RE.sub("", lineas[j]).strip()
                if cand:
                    ciclo = cand
                    break
            if not title:
                continue

            fin_bloque = fichas[n + 1] - 1 if n + 1 < len(fichas) else len(lineas)
            bloque = lineas[i + 1:fin_bloque]
            fin_anterior = fin_bloque - 1

            duration: Optional[int] = None
            ticket = ARTHAUS_CINE_URL
            funcs: set = set()
            for l in bloque:
                if _ARTHAUS_LINK_RE.match(l):
                    if link_k < len(hrefs):
                        ticket = hrefs[link_k]
                    link_k += 1
                mdur = _ARTHAUS_DUR_RE.search(l)
                if mdur:
                    duration = int(mdur.group(1))
                for m in _ARTHAUS_DATE_RE.finditer(l):
                    month = MESES_ES.get(m.group(2).lower())
                    if not month:
                        continue
                    hora = f"{int(m.group(3)):02d}:{m.group(4) or '00'}"
                    for day in (int(x) for x in re.findall(r"\d{1,2}", m.group(1))):
                        for y in (today.year, today.year + 1):
                            try:
                                d = date(y, month, day)
                            except ValueError:
                                continue
                            if today <= d <= cutoff:
                                funcs.add((d.isoformat(), hora))
                                break

            for fecha, hora in sorted(funcs):
                result.append(Screening(
                    cine="Arthaus", title=title, fecha=fecha, hora=hora,
                    ticket_url=ticket, director=director, duration=duration,
                    ciclo=ciclo,
                ))
    return result


# ---------------------------------------------------------------------------
# Centro Cultural 25 de Mayo — cc25.org/cine (Cine Urquiza, Villa Urquiza)
# WordPress: /cine/ lista cards con "Ver detalle" → /eventos/<slug>/ con
# FECHA / HORA / CATEGORÍA (Cine) + director/año/duración. Igual que Arthaus.
# ---------------------------------------------------------------------------

CC25_CINE_URL = "https://cc25.org/cine/"
_CC25_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _parse_cc25_detail(h1: str, body: str, url: str,
                       today: date, cutoff: date) -> list[Screening]:
    """Parsea una página /eventos/ de cc25.org. Sólo si CATEGORÍA incluye 'cine'."""
    flat = re.sub(r"[ \t]+", " ", body or "")
    low = flat.lower()
    mcat = re.search(r"categor[ií]a\s*(.{0,40})", low, re.DOTALL)
    if not (mcat and "cine" in mcat.group(1)):
        return []
    mf = re.search(r"fecha\s+(\d{1,2})\s+([a-záéíóú]{3})[a-záéíóú.]*\s+(\d{4})", low)
    if not mf:
        return []
    day, mon, yr = int(mf.group(1)), _CC25_MONTHS.get(mf.group(2)), int(mf.group(3))
    if not mon:
        return []
    mh = re.search(r"hora\s+(\d{1,2}:\d{2})", low)
    hora = mh.group(1) if mh else "20:00"

    h1 = (h1 or "").strip()
    # Director: CC25 lo pone en el H1 como "Título – de Director" (limpio);
    # fallback al cuerpo "dirigido por ...".
    director = ""
    md2 = re.search(r"[–-]\s*de\s+([^\n]+?)\s*$", h1, re.IGNORECASE)
    if md2:
        director = md2.group(1).strip()
    else:
        md = re.search(r"dirigid[oa]\s+por\s+([^,\n.]+?)(?:\s+y\s+(?:protagoniz|producid)|\s*[,.]|$)",
                       flat, re.IGNORECASE)
        if md:
            director = md.group(1).strip()
    title = re.sub(r"\s*[–-]\s*de\s+.*$", "", h1, flags=re.IGNORECASE).strip()
    if director:
        title = re.sub(r"\s*[–-]?\s*de\s+" + re.escape(director) + r"\s*$", "", title,
                       flags=re.IGNORECASE).strip()
    if not title:
        return []

    film_year: Optional[int] = None
    country = ""
    my = re.search(r"\b([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s*/\s*[A-ZÁÉÍÓÚ][a-záéíóúñ]+)?)\s*,\s*((?:19|20)\d{2})\b", flat)
    if my:
        country, film_year = my.group(1).strip(), int(my.group(2))
    else:
        ym = re.search(r"\b((?:19|20)\d{2})\b", flat)
        if ym:
            film_year = int(ym.group(1))
    mdur = re.search(r"duraci[óo]n:?\s*(\d{1,3})", low)
    duration = int(mdur.group(1)) if mdur else None

    try:
        d = date(yr, mon, day)
    except ValueError:
        return []
    if not (today <= d <= cutoff):
        return []
    return [Screening(
        cine="Centro Cultural 25 de Mayo", title=title,
        fecha=d.isoformat(), hora=hora, ticket_url=url,
        director=director, country=country, year=film_year, duration=duration,
    )]


def _inner_text(soup) -> str:
    """Equivalente a document.body.innerText sobre HTML servido: un salto de
    línea por nodo y sin el contenido de script/style/noscript, que get_text()
    incluiría y ensuciaría los regex de fecha/hora."""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = (re.sub(r"[ \t]+", " ", l).strip() for l in soup.get_text("\n").splitlines())
    return "\n".join(l for l in lines if l)


def scrape_cc25(semanas: int = 3) -> list[Screening]:
    """Scrapea cc25.org/cine: junta los links de eventos (/eventos/) y entra a
    cada uno a sacar fecha/hora/título/director (filtrando CATEGORÍA = Cine).

    Sin playwright: el HTML servido ya trae la listing completa y las fichas de
    cada evento. Con browser el scrape venía devolviendo 0 desde mediados de
    julio (el goto se colgaba en el runner sobre una página de ~460 KB), y
    encima el parser andaba perfecto — se perdían las funciones por el
    transporte, no por el parseo.

    Ojo: /cine/ mezcla eventos vigentes con un archivo de funciones viejas
    (marcadas "¡Caducado!"). El filtro por ventana de fechas ya las descarta.
    """
    today = date.today()
    cutoff = today + timedelta(weeks=max(semanas, 6))
    try:
        listing = fetch_html(CC25_CINE_URL)
    except Exception as e:
        print(f"[cc25: listing no carga — {e}]", end=" ", flush=True)
        return []

    links: list[str] = []
    for a in listing.find_all("a", href=re.compile(r"/eventos/")):
        u = a["href"]
        if not u.startswith("http"):
            u = "https://cc25.org" + ("" if u.startswith("/") else "/") + u
        u = u.split("?")[0].split("#")[0]
        if u not in links:
            links.append(u)
    if not links:
        print("[cc25: 0 links de evento en la listing]", end=" ", flush=True)

    result: list[Screening] = []
    for url in links[:40]:
        try:
            soup = fetch_html(url)
        except Exception:
            continue
        h1 = soup.find("h1")
        result.extend(_parse_cc25_detail(
            h1.get_text(" ", strip=True) if h1 else "",
            _inner_text(soup), url, today, cutoff))
    return result


# ---------------------------------------------------------------------------
# Centro Cultural Borges — centroculturalborges.gob.ar
# Consume la API pública del sitio eliminando la necesidad de automatizar el
# navegador. Combina los datos de la cartelera general con los detalles de
# cada evento para estructurar películas, directores, fechas y horarios.
# ---------------------------------------------------------------------------

BORGES_API_LIST = "https://centroculturalborges.gob.ar/api/public/eventos-destacados?disciplina=cine"
BORGES_API_DETAIL = "https://centroculturalborges.gob.ar/api/public/evento-detalle?id="

_BORGES_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_BORGES_WD = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
_BORGES_ACCENTS = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

_BORGES_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*\.?\s+(20\d{2})\b",
    re.IGNORECASE,
)
_BORGES_RANGE_RE = re.compile(
    r"\bde\s+(lun|mar|mi[ée]|jue|vie|s[áa]b|dom)\w*\s+a\s+(lun|mar|mi[ée]|jue|vie|s[áa]b|dom)\w*",
    re.IGNORECASE,
)

def _borges_wd(tok: str) -> Optional[int]:
    return _BORGES_WD.get(tok.translate(_BORGES_ACCENTS).lower()[:3])

def _borges_dates_from_label(label: str, today: date, cutoff: date) -> list[date]:
    """Convierte el encabezado de fecha de la API en fechas concretas."""
    out: list[date] = []
    m = _BORGES_DATE_RE.search(label)
    if m:
        mon = _BORGES_MONTHS.get(m.group(2).lower()[:3])
        if mon:
            try:
                d = date(int(m.group(3)), mon, int(m.group(1)))
                if today <= d <= cutoff:
                    out.append(d)
            except ValueError:
                pass
        return out
    mr = _BORGES_RANGE_RE.search(label)
    if mr:
        a, b = _borges_wd(mr.group(1)), _borges_wd(mr.group(2))
        if a is None or b is None:
            return out
        wanted, i = set(), a
        for _ in range(7):
            wanted.add(i)
            if i == b:
                break
            i = (i + 1) % 7
        rng_cut = min(cutoff, today + timedelta(days=8))
        d = today
        while d <= rng_cut:
            if d.weekday() in wanted:
                out.append(d)
            d += timedelta(days=1)
    return out

def _borges_http_json(url: str, browser_headers: bool = True, timeout: int = 45):
    """GET + parseo JSON. Con headers de navegador para el intento directo, o
    mínimos cuando va por el servicio de scraping (que pone los suyos)."""
    headers = {"Accept": "application/json, text/plain, */*"}
    if browser_headers:
        headers.update({
            "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                           "Version/18.5 Mobile/15E148 Safari/604.1"),
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
            "Referer": "https://centroculturalborges.gob.ar/disciplinas?d=cine",
            "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"iOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_borges_json(url: str, *, critical: bool = True,
                      context: str = "") -> Optional[dict | list]:
    """Trae un JSON de la API del Borges. Primero prueba directo (headers de
    navegador). Si Cloudflare bloquea la IP del runner, reintenta a través de un
    servicio de scraping con IPs residenciales — sólo si está configurado el
    secret SCRAPER_KEY. Si todo falla, devuelve None (Borges queda vacío
    sin romper el resto del scrapeo).

    `critical` controla el logueo, no el comportamiento:
      · listado  → crítico: si falla, Borges queda en 0 → se loguea como error.
      · detalle  → NO crítico: la función igual se arma con los datos del
                   listado, así que su fallo es silencioso (el llamador lo
                   resume al final). Antes se imprimía un "[Borges API Error]"
                   por cada detalle caído y hacía parecer roto un scrape sano.
    `context` es la etiqueta legible del recurso ("el listado de cine")."""
    try:
        return _borges_http_json(url, browser_headers=True)
    except Exception as direct_err:
        proxy = _scraper_proxy_url(url)
        if not proxy:
            if critical:
                print(f"  · ❌ [Borges] No se pudo traer {context or 'el recurso'}: "
                      f"{direct_err} (configurá SCRAPER_KEY para un proxy residencial)")
            return None
        # El servicio de scraping (residencial + anti-Cloudflare) suele tardar
        # 60-90s en resolver el challenge de CF: timeout amplio + un reintento
        # (a veces la 1ra pasada falla transitoriamente).
        proxy_err: Optional[Exception] = None
        for _ in range(2):
            try:
                return _borges_http_json(proxy, browser_headers=False, timeout=120)
            except Exception as e:
                proxy_err = e
                if _credencial_del_proxy_caida(e):
                    break      # no es transitorio: reintentar sólo quema tiempo
        if critical:
            print(f"  · ❌ [Borges] No se pudo traer {context or 'el recurso'} "
                  f"(directo: {direct_err}; proxy: {proxy_err})"
                  f"{_pista_credencial(proxy_err)}")
        return None

def _borges_times_from_rep(rep: str, sig_hora: str) -> list[str]:
    """Horarios de un evento desde fechasRepeticiones — SÓLO la parte a la
    derecha del guión (p.ej. '15, 17 y 19 h' o '14:50, 16:20, 17:50, 19:20 h').
    NO se parsea la descripción larga porque ahí las duraciones de los cortos
    ('(00:08:00)') se colarían como horarios falsos. Fallback: horarioSiguiente."""
    tail = re.split(r"\s*[-–—]\s*", rep or "", maxsplit=1)
    tail = tail[1] if len(tail) > 1 else ""
    times: list[str] = []
    for hh, mm in re.findall(r"(\d{1,2})(?::(\d{2}))?", tail):
        if 0 <= int(hh) <= 23:
            times.append(f"{int(hh):02d}:{mm or '00'}")
    if not times and sig_hora:
        m = re.match(r"(\d{1,2}):(\d{2})", sig_hora)
        if m:
            times.append(f"{int(m.group(1)):02d}:{m.group(2)}")
    return list(dict.fromkeys(times))


def _borges_dates_from_rep(rep: str, display: str, sig_iso: str,
                           today: date, cutoff: date) -> list[date]:
    """Fechas de un evento, por prioridad:
      1) día(s)+mes explícitos en fechasRepeticiones ('Mie 1 / 8 / 15 jul …') →
         captura festivales con varias fechas.
      2) fechaDisplay ('01 JUL 2026' puntual o 'DE MIE A DOM' rango semanal).
      3) fechaSiguienteRepeticion (ISO)."""
    left = re.split(r"\s*[-–—]\s*", rep or "", maxsplit=1)[0]
    mm = re.search(r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)", left, re.IGNORECASE)
    days = [int(x) for x in re.findall(r"\b(\d{1,2})\b", left)]
    if mm and days:
        mon = _BORGES_MONTHS.get(mm.group(1).lower()[:3])
        ym = re.search(r"(20\d{2})", display or "")
        yr = int(ym.group(1)) if ym else today.year + (1 if mon and mon < today.month else 0)
        out = []
        for d in days:
            try:
                dt = date(yr, mon, d)
            except (ValueError, TypeError):
                continue
            if today <= dt <= cutoff:
                out.append(dt)
        if out:
            return out
    lab = _borges_dates_from_label(display or "", today, cutoff)
    if lab:
        return lab
    if sig_iso:
        try:
            d = date.fromisoformat(sig_iso[:10])
            if today <= d <= cutoff:
                return [d]
        except ValueError:
            pass
    return []


async def scrape_borges(page: Page, semanas: int = 3) -> list[Screening]:
    """Scrapea centroculturalborges.gob.ar consumiendo sus endpoints JSON
    públicos (el HTML está detrás de un challenge anti-bots, pero la API no).
    Conserva `page` intacto para no romper el contrato de run.py."""
    today = date.today()
    cutoff = today + timedelta(weeks=max(semanas, 6))
    print("  · Conectando a la API del Centro Cultural Borges...", flush=True)
    events_list = fetch_borges_json(BORGES_API_LIST, critical=True,
                                    context="el listado de cine")
    if not events_list or not isinstance(events_list, list):
        # Único fallo realmente fatal: sin listado no hay nada. run.py detecta
        # que Borges vino con <3 funciones y restaura las futuras del caché.
        print("  · [Borges] Listado inaccesible → se conserva la programación "
              "de la corrida anterior (caché).")
        return []

    result: list[Screening] = []
    seen: set = set()
    detail_missing = 0  # detalles caídos (no crítico) — se resumen al final
    for ev in events_list:
        if not isinstance(ev, dict):
            continue
        ev_id = ev.get("id")
        title = re.sub(r'["“”]', "", ev.get("titulo", "") or "")
        title = re.sub(r"\s+", " ", title).strip()
        if not ev_id or not title:
            continue

        # El detalle sólo aporta algo que el listado no tiene cuando el evento
        # tiene rango de fechas ("DE MIE A DOM") o es un festival con varias
        # fechas/horarios. Para las funciones de fecha única, el listado ya trae
        # fecha + horario, así ahorramos llamadas al servicio de scraping.
        display = ev.get("fechaDisplay", "") or ""
        needs_detail = bool(_BORGES_RANGE_RE.search(display)
                            or re.search(r"festival|ciclo", title, re.IGNORECASE))
        detail: dict = {}
        if needs_detail:
            detail_json = fetch_borges_json(
                f"{BORGES_API_DETAIL}{ev_id}", critical=False,
                context=f"el detalle del evento {ev_id}")
            if detail_json is None:
                detail_missing += 1  # no crítico: seguimos con datos del listado
            elif isinstance(detail_json, dict):
                detail = detail_json
        rep = detail.get("fechasRepeticiones", "") or ""

        director = (ev.get("artistaDestacado") or "").strip()
        duration = detail.get("duracion")
        if not isinstance(duration, int) or duration <= 0:
            duration = None

        times = _borges_times_from_rep(rep, ev.get("horarioSiguienteRepeticion") or "") or ["19:00"]
        dates = _borges_dates_from_rep(
            rep, ev.get("fechaDisplay", "") or "",
            ev.get("fechaSiguienteRepeticion") or "", today, cutoff)
        if not dates:
            continue

        ticket_url = f"https://centroculturalborges.gob.ar/evento/{ev_id}"
        for d in dates:
            for t in times:
                key = (title, d.isoformat(), t)
                if key in seen:
                    continue
                seen.add(key)
                result.append(Screening(
                    cine="Centro Cultural Borges",
                    title=title,
                    fecha=d.isoformat(),
                    hora=t,
                    ticket_url=ticket_url,
                    director=director,
                    duration=duration,
                ))

    if detail_missing:
        # Aviso tranquilo, NO error: el detalle sólo aporta fechas extra a
        # festivales/ciclos; sin él, cada función igual queda con la fecha/hora
        # del listado.
        print(f"  · ⚠️  [Borges] {detail_missing} evento(s) sin detalle "
              "(no crítico: se usó la fecha/hora del listado).")
    print(f"  · ✅ [Borges] {len(result)} funciones procesadas.")
    return result


def scrape_lumiton_agenda() -> list[Screening]:
    """
    Scrapea https://lumiton.ar/agenda-presencial/ — un único endpoint estático
    (urllib, sin playwright) que lista TODAS las funciones próximas para los
    3 venues. Cada <article.evento> tiene `data-date`, `data-locations`,
    título en <h3> y link al evento. Entradas siempre son gratuitas (orden de
    llegada), así que `ticket_url` apunta a la página del evento.
    """
    try:
        soup = fetch_html("https://lumiton.ar/agenda-presencial/")
    except Exception:
        return []

    result: list[Screening] = []
    seen: set[tuple] = set()

    for art in soup.select("article.evento"):
        # Date — directly from the data-date attribute (YYYY-MM-DD)
        fecha = art.get("data-date") or ""
        try:
            date.fromisoformat(fecha)
        except ValueError:
            continue

        # Venue — first slug in data-locations
        locations_raw = art.get("data-locations", "")
        venue_slug = ""
        m = re.search(r'"([a-z0-9-]+)"', locations_raw)
        if m:
            venue_slug = m.group(1)
        cine = LUMITON_VENUES.get(venue_slug)
        if not cine:
            continue  # skip unknown venues (workshops at other locations)

        # Time — find a "HH:MMhs" token in the date header
        hora = "??"
        for div in art.find_all("div"):
            t = div.get_text(strip=True)
            tm = re.match(r"^(\d{1,2}):(\d{2})hs$", t)
            if tm:
                hora = f"{int(tm.group(1)):02d}:{tm.group(2)}"
                break

        # Title
        title_el = art.find("h3")
        if not title_el:
            continue
        title = re.sub(r"\s+", " ", title_el.get_text(strip=True))
        if not title:
            continue

        # Event link (free entry — link goes to the event page with details)
        link_el = art.find("a", href=re.compile(r"/evento/"))
        ticket_url = link_el["href"] if link_el and link_el.get("href") else ""

        key = (cine, title, fecha, hora)
        if key in seen:
            continue
        seen.add(key)
        result.append(Screening(
            cine=cine, title=title, fecha=fecha, hora=hora,
            ticket_url=ticket_url,
        ))

    # Enrich each screening with director / país / duración from its evento page.
    # Multiple screenings can share the same ticket_url (e.g. weekly cycle), so cache per URL.
    meta_cache: dict[str, dict] = {}
    for s in result:
        if not s.ticket_url:
            continue
        if s.ticket_url not in meta_cache:
            meta_cache[s.ticket_url] = fetch_lumiton_evento_meta(s.ticket_url)
        meta = meta_cache[s.ticket_url]
        s.director = meta.get("director", "")
        s.country = meta.get("country", "")
        s.year = meta.get("year")
        s.duration = meta.get("duration")

    return result


# ---------------------------------------------------------------------------
# Museo del Cine Pablo Ducrós Hicken
#   index → /gcaba_historico/cultura/museos/museodelcine
#   por mes → /gcaba_historico/noticias/<MES>-en-el-museo-del-cine[-N]
# Cada nota lista las funciones con este patrón:
#   Sábado 2 a las 16 h | Cineclub Infantil
#   El héroe del río de Buster Keaton y Charles Reisner (1928, Steamboat Bill, Jr.)
# ---------------------------------------------------------------------------

MUSEOCINE_BASE = "https://buenosaires.gob.ar"
MUSEOCINE_INDEX = MUSEOCINE_BASE + "/gcaba_historico/cultura/museos/museodelcine"
MUSEO_MANUAL_PATH = Path(__file__).parent / "data" / "museo_manual.json"


def _museo_manual(today: date, cutoff: date) -> list[Screening]:
    """Override manual (data/museo_manual.json). Se mergea con el scrape y se
    filtra a la ventana; las funciones de meses pasados se caen solas."""
    if not MUSEO_MANUAL_PATH.exists():
        return []
    try:
        data = json.loads(MUSEO_MANUAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: list[Screening] = []
    for s in data.get("screenings", []):
        title = (s.get("title") or "").strip()
        try:
            d = date.fromisoformat(s["fecha"])
        except (KeyError, ValueError):
            continue
        if not title or not (today <= d <= cutoff):
            continue
        out.append(Screening(
            cine="Museo del Cine", title=title,
            fecha=s["fecha"], hora=s.get("hora", "??"),
            ticket_url=MUSEOCINE_INDEX, ciclo=s.get("ciclo", ""),
            director=s.get("director", ""), year=s.get("year"),
            original_title=s.get("original_title", ""),
        ))
    return out

_MUSEOCINE_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# La nota mensual es una noticia cuyo slug arranca con el nombre del mes
# ("junio-en-nuestro-auditorio-0", "mayo-en-el-museo-del-cine", ...). El museo
# va cambiando el sufijo (auditorio / museo-del-cine / etc.), así que NO nos
# atamos a él: descubrimos por el prefijo de mes, que es la parte estable.
_MUSEOCINE_NOTICIA_RE = re.compile(
    r"/noticias/(?:" + "|".join(_MUSEOCINE_MONTHS) + r")-", re.IGNORECASE
)


def _museocine_month_pages() -> list[str]:
    """Lista URLs absolutas de las notas mensuales linkeadas desde el índice.

    Detecta cualquier noticia cuyo slug empiece con un nombre de mes, sin
    depender del sufijo (que el museo cambia). Las notas de meses pasados que se
    cuelen las descarta después el filtro de ventana de fechas.
    """
    try:
        soup = fetch_html(MUSEOCINE_INDEX)
    except Exception:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=_MUSEOCINE_NOTICIA_RE):
        h = a.get("href", "")
        if not h:
            continue
        if h.startswith("/"):
            h = MUSEOCINE_BASE + h
        if h not in seen:
            seen.add(h)
            urls.append(h)
    return urls


_MUSEO_PAREN_RE = re.compile(r"^(.+?)\s+\(([^)]*)\)\s*$")


def _museo_film_parts(cand: str):
    """De "Título de Director (...año...)" devuelve (title, director, year, original).

    El split título/director es ambiguo cuando hay varios " de " (títulos con
    "de": El mago de Oz; o directores con "de": Alberto de Zavalía). Probamos
    todos los " de " donde el director arranca en mayúscula y elegimos el que
    deja un director con forma de nombre (2-3 palabras; desempate: más palabras).
    Devuelve None si no parece una línea de película.
    """
    m = _MUSEO_PAREN_RE.match(cand)
    if not m:
        return None
    prefix, paren = m.group(1), m.group(2)
    ym = re.search(r"\b((?:19|20)\d{2})\b", paren)
    if not ym:
        return None
    year = int(ym.group(1))
    original = re.sub(r"\b(?:19|20)\d{2}\b", "", paren).strip(" ,").strip()

    best = None  # (score, title, director)
    for mde in re.finditer(r"\sde\s", prefix):
        title = prefix[:mde.start()].strip()
        director = prefix[mde.end():].strip()
        if not title or not director or not director[:1].isupper():
            continue
        w = len(director.split())
        score = (-abs(w - 2), w)  # preferir 2-3 palabras; desempate: más palabras
        if best is None or score > best[0]:
            best = (score, title, director)
    if not best:
        return None
    return best[1], re.sub(r"\s+", " ", best[2]).strip(), year, original


def _parse_museocine_page(text: str, slug_month: Optional[int],
                          today: Optional[date] = None) -> list[dict]:
    """
    Parsea texto plano de una nota mensual del Museo del Cine.
    Devuelve [{fecha, hora, title, ciclo, director, year, original_title}, ...].
    """
    today = today or date.today()
    out: list[dict] = []

    # Año: lo tomamos del header "Martes 05 de Mayo de 2026" o de "de 2026"
    year = date.today().year
    ym = re.search(r"\bde\s+(20\d{2})\b", text)
    if ym:
        year = int(ym.group(1))

    # Mes: priorizar mes del slug; sino, detectar en el cuerpo
    month = slug_month
    if month is None:
        for m_name, m_num in _MUSEOCINE_MONTHS.items():
            if m_name in text.lower():
                month = m_num
                break
    if month is None:
        return []

    # Header de función. El museo MEZCLA formatos en la misma nota:
    #   "Sábado 6 a las 16 h"                              (sin mes)
    #   "Sábado 20 de junio a las 16 h | Comunidad ..."    (con "de mes")
    #   "Domingo 21 de junio | a partir de las 16 h"       ("| a partir de las")
    #   "Domingo 21 y domingo 28 de junio a las 18 h | ..."(rango de 2 días)
    #   "Domingo 7 a las 18 h I Cine argentino en video"   (separador "I")
    _wd = r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)"
    _mon = "|".join(_MUSEOCINE_MONTHS)
    header_re = re.compile(
        _wd + r"\s+(?P<d1>\d{1,2})"
        r"(?:\s+y\s+(?:" + _wd + r"\s+)?(?P<d2>\d{1,2}))?"     # rango opcional "21 y (domingo) 28"
        r"(?:\s+de\s+(?P<mon>" + _mon + r"))?"                 # "de junio" opcional
        r"\s*\|?\s*"                                            # "|" opcional antes del horario
        r"a\s+(?:las|partir\s+de\s+las)\s+"                     # "a las" / "a partir de las"
        r"(?P<hh>\d{1,2})(?:[.:](?P<mm>\d{2}))?\s*h(?:s|oras)?"
        r"(?:\s*[|I¦]\s*(?P<ciclo>[^\n]+))?",
        re.IGNORECASE,
    )
    # "Título de Director (...)" — non-greedy en title, pero requiere que el
    # director empiece con mayúscula para no cortar en preposiciones internas
    # del título ("de las ostras", "de la calle"). El paréntesis se captura
    # entero porque el museo escribe tanto "(AÑO)" / "(AÑO, Original)" como
    # "(Original, AÑO)"; el año se extrae después, esté donde esté.
    # Iteramos por cada match de header y escaneamos las líneas del segmento
    # (hasta el próximo header) buscando la primera que sea una línea de película.
    matches = list(header_re.finditer(text))
    # Agrupamos matches contiguos de la MISMA línea de fecha (separados sólo por
    # " y [díasemana] "): comparten la película que viene después, y cada uno
    # aporta su propio horario → soporta "día X a las Hh y día Y a las Kh".
    groups: list[list] = []
    for hm in matches:
        if groups and re.fullmatch(rf"\s*y\s*(?:{_wd}\s*)?",
                                   text[groups[-1][-1].end():hm.start()], re.IGNORECASE):
            groups[-1].append(hm)
        else:
            groups.append([hm])

    for gi, group in enumerate(groups):
        # Slots (día, mes, hora, minuto) de todo el grupo + ciclo.
        slots: list[tuple] = []
        ciclo = ""
        for hm in group:
            hmonth = _MUSEOCINE_MONTHS.get(hm.group("mon").lower()) if hm.group("mon") else month
            hour = int(hm.group("hh"))
            minute = int(hm.group("mm") or 0)
            days = [int(hm.group("d1"))]
            if hm.group("d2"):
                days.append(int(hm.group("d2")))
            for dn in days:
                slots.append((dn, hmonth, hour, minute))
            if hm.group("ciclo"):
                ciclo = hm.group("ciclo").strip().rstrip(".,;")
                # El museo redacta "NOMBRE DEL CICLO presenta" — nos quedamos
                # sólo con el nombre del ciclo.
                ciclo = re.sub(r"\s+presenta$", "", ciclo, flags=re.IGNORECASE).strip()

        # Película: segmento desde el fin del grupo hasta el próximo grupo.
        seg_start = group[-1].end()
        seg_end = groups[gi + 1][0].start() if gi + 1 < len(groups) else len(text)
        # El título y el "de Director (año)" a veces quedan en la MISMA línea y a
        # veces partidos (un <strong> los separa en get_text), así que probamos
        # uniendo hasta 4 líneas consecutivas desde el inicio del segmento.
        seg_lines = [ln.strip() for ln in text[seg_start:seg_end].splitlines() if ln.strip()]
        title = director = original = ""
        film_year: Optional[int] = None
        for span in range(1, 5):
            for start in range(min(5, len(seg_lines))):
                parts = _museo_film_parts(" ".join(seg_lines[start:start + span]))
                if parts:
                    title, director, film_year, original = parts
                    break
            if title:
                break
        if not title and seg_lines:
            # Sin "Título de Director (año)": p.ej. un ciclo de cortos
            # ("Futuras: …") o un film cuyo director no está en la línea
            # ("Tambores apaches (Apache Drums, 1951, EE.UU.)"). Limpiamos el
            # paréntesis final y sacamos año/título original si están.
            first = seg_lines[0]
            pm = re.search(r"\(([^)]*)\)\s*$", first)
            if pm:
                py = re.search(r"\b((?:19|20)\d{2})\b", pm.group(1))
                if py:
                    film_year = int(py.group(1))
                orig = re.sub(r"\b(?:19|20)\d{2}\b|EE\.?\s*UU\.?", " ", pm.group(1))
                orig = re.sub(r"\s+", " ", orig).strip(" ,.")
                if orig:
                    original = orig
                first = first[:pm.start()].strip()
            if 3 <= len(first) <= 100 and (first[:1].isupper() or first[:1] in "¡¿"):
                title = first
        if not title:
            continue

        for dn, hmonth, hour, minute in slots:
            # Corrección de typo de mes: el museo a veces escribe "de junio" en
            # la nota de julio. Si el mes explícito manda la fecha al pasado
            # pero el mes del slug la deja a futuro, usamos el del slug.
            d: Optional[date] = None
            try:
                d = date(year, hmonth, dn)
            except (ValueError, TypeError):
                pass
            if slug_month and hmonth != slug_month and (d is None or d < today):
                try:
                    ds = date(year, slug_month, dn)
                    if ds >= today:
                        d = ds
                except ValueError:
                    pass
            if d is None:
                continue
            out.append({
                "fecha": d.isoformat(),
                "hora": f"{hour:02d}:{minute:02d}",
                "title": title,
                "director": director,
                "year": film_year,
                "original_title": original,
                "ciclo": ciclo,
            })
    return out


def scrape_museo_cine(semanas: int = 4) -> list[Screening]:
    """
    Scrapea el index del Museo del Cine, descarga las notas mensuales
    linkeadas y extrae las funciones dentro de la ventana (hoy → hoy+semanas).
    """
    today = date.today()
    cutoff = today + timedelta(weeks=semanas)
    page_urls = _museocine_month_pages()
    result: list[Screening] = []
    seen: set[tuple] = set()

    for url in page_urls:
        # Mes desde el slug (mayo|abril|...)
        slug_month: Optional[int] = None
        for m_name, m_num in _MUSEOCINE_MONTHS.items():
            if f"/{m_name}-" in url or url.endswith(f"/{m_name}-en-el-museo-del-cine"):
                slug_month = m_num
                break

        try:
            soup = fetch_html(url)
        except Exception:
            continue
        # Acotar al contenido principal — saca menú/footer
        main = soup.find("article") or soup.find("main") or soup
        text = main.get_text("\n", strip=True)

        for ev in _parse_museocine_page(text, slug_month, today):
            try:
                d = date.fromisoformat(ev["fecha"])
            except ValueError:
                continue
            if d < today or d > cutoff:
                continue
            key = (ev["title"], ev["fecha"], ev["hora"])
            if key in seen:
                continue
            seen.add(key)
            result.append(Screening(
                cine="Museo del Cine",
                title=ev["title"],
                fecha=ev["fecha"],
                hora=ev["hora"],
                ticket_url=url,
                ciclo=ev.get("ciclo", ""),
                director=ev.get("director", ""),
                year=ev.get("year"),
                original_title=ev.get("original_title", ""),
            ))

    # Override manual (stopgap) — dedup contra lo scrapeado.
    for s in _museo_manual(today, cutoff):
        key = (s.title, s.fecha, s.hora)
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# Centro Cultural Recoleta (CCR) — categoria=9 = Cine
#   Index → /agenda?categoria=9
#   Cada link es un evento individual o un ciclo con "Actividades" hijas.
#   Formato de fechas: "Sáb. 02.05 y Sáb. 30.05 | 18 h | Cine"
# ---------------------------------------------------------------------------

CCR_BASE = "http://centroculturalrecoleta.org"
CCR_INDEX = CCR_BASE + "/agenda?categoria=9"


def scrape_ccr() -> list[Screening]:
    today = date.today()
    cutoff = today + timedelta(days=90)
    try:
        idx_soup = fetch_html(CCR_INDEX)
    except Exception:
        return []

    event_urls: list[str] = []
    seen_urls: set[str] = set()
    for a in idx_soup.find_all("a", href=re.compile(r"^/agenda/")):
        h = a.get("href", "")
        if not h or "categoria" in h:
            continue
        u = CCR_BASE + h if h.startswith("/") else h
        if u not in seen_urls:
            seen_urls.add(u)
            event_urls.append(u)

    # Línea de fechas: precedida por DíaAbbr y con DD.MM + HH
    date_line_re = re.compile(
        r"(?:Lun|Mar|Mi[ée]|Jue|Vie|S[áa]b|Dom)\.\s+\d{1,2}\.\d{1,2}",
        re.IGNORECASE,
    )
    # Para extraer todos los DD.MM
    ddmm_re = re.compile(r"\b(\d{1,2})\.(\d{1,2})\b")
    hour_re = re.compile(r"(\d{1,2})(?:[.:](\d{2}))?\s*h\b", re.IGNORECASE)

    result: list[Screening] = []
    seen_keys: set[tuple] = set()

    for url in event_urls:
        try:
            soup = fetch_html(url)
        except Exception:
            continue
        text = soup.get_text("\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines()]

        # Iterar líneas; cada línea que matchee date_line_re es una función,
        # y el título es la línea no-vacía inmediata anterior.
        for i, line in enumerate(lines):
            if not date_line_re.search(line):
                continue
            # Skip the index-style "Sábados y domingos de mayo" header
            if not ddmm_re.search(line):
                continue

            title = ""
            j = i - 1
            while j >= 0:
                cand = lines[j].strip()
                if cand and not date_line_re.search(cand):
                    title = cand
                    break
                j -= 1
            if not title or title.startswith("#") or len(title) < 2:
                continue
            # Filtrar headers genéricos
            if title.lower() in {"actividades", "horarios", "cine"}:
                continue

            # El título viene prefijado con la categoría ("Cine | …", "Taller |
            # …", "Música | …"). Sólo cine; se saca el prefijo. Además, si la
            # línea de fecha trae la categoría al final ("| 18 h | Taller"),
            # descartamos lo que no sea cine.
            pm = re.match(r"^([A-Za-zÁÉÍÓÚáéíóúñ]+)\s*\|\s*(.+)$", title)
            if pm:
                if pm.group(1).strip().lower() != "cine":
                    continue
                title = pm.group(2).strip()
            segs = [s.strip() for s in line.split("|") if s.strip()]
            if len(segs) >= 2 and re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúñ ]{3,}", segs[-1]) \
                    and "cine" not in segs[-1].lower():
                continue

            hm = hour_re.search(line)
            if not hm:
                continue
            hour = int(hm.group(1))
            minute = int(hm.group(2) or 0)
            hora = f"{hour:02d}:{minute:02d}"

            for dm in ddmm_re.finditer(line):
                day = int(dm.group(1))
                month = int(dm.group(2))
                # Año: mes pasado → próximo año
                year = today.year
                if month < today.month:
                    year += 1
                try:
                    d = date(year, month, day)
                except ValueError:
                    continue
                if d < today or d > cutoff:
                    continue
                key = (title, d.isoformat(), hora)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                result.append(Screening(
                    cine="Centro Cultural Recoleta",
                    title=title,
                    fecha=d.isoformat(),
                    hora=hora,
                    ticket_url=url,
                ))
    return result


# ---------------------------------------------------------------------------
# Amorina Cine Bar  (amorina.club — JSON API pública con schedule completo)
# ---------------------------------------------------------------------------

def scrape_amorina() -> list[Screening]:
    """
    Lee https://www.amorina.club/schedule.json — array con una entrada por
    función. Cada item tiene title, showtime (ISO con TZ), director, year,
    runtime_mins, nationality, imdbid, overview, poster, etc.
    """
    import json as _json
    url = "https://www.amorina.club/schedule.json"
    try:
        data = _json.loads(fetch_bytes(url).decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[amorina: {type(e).__name__} — {e}]", end=" ", flush=True)
        return []

    if not isinstance(data, list):
        return []

    result: list[Screening] = []
    today = date.today()
    for item in data:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        showtime = (item.get("showtime") or "").strip()
        if not title or not showtime:
            continue
        # Parsear ISO: "2026-05-24T21:00:00-03:00"
        try:
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(showtime)
        except Exception:
            continue
        # Filtrar pasado
        if dt.date() < today:
            continue
        fecha = dt.date().isoformat()
        hora = f"{dt.hour:02d}:{dt.minute:02d}"

        director = (item.get("director") or "").strip()
        nationality = (item.get("nationality") or "").strip()
        year = item.get("year")
        try:
            year = int(year) if year else None
        except (TypeError, ValueError):
            year = None
        duration = item.get("runtime_mins")
        try:
            duration = int(duration) if duration else None
        except (TypeError, ValueError):
            duration = None
        ciclo = (item.get("genre") or "").strip()

        result.append(Screening(
            cine="Amorina",
            title=title,
            fecha=fecha,
            hora=hora,
            ticket_url="https://www.amorina.club/peliculas",
            ciclo=ciclo if ciclo and ciclo.lower() != "amorina elige" else "",
            director=director,
            country=nationality,
            year=year,
            duration=duration,
        ))
    return result


# ---------------------------------------------------------------------------
# CEA — Centro de Experimentación Audiovisual (Avellaneda)
# cea.mda.gob.ar — sitio rediseñado (scroll/SPA). Parseamos el texto renderizado
# (vía playwright) en vez de clases CSS, que el sitio renombra seguido.
# Cada función: día → "Weekday Mes" → título → "Director · Año".
# ---------------------------------------------------------------------------

_CEA_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_CEA_ACCENTS = str.maketrans("áéíóúü", "aeiouu")
_CEA_WD_FULL = r"lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo"
_CEA_DIR_YEAR_RE = re.compile(r"^(.+?)\s+·\s+((?:19|20)\d{2})\b")


def _cea_norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").translate(_CEA_ACCENTS).lower()).strip()


def _parse_cea_text(text: str, today: date, cutoff: date) -> list[dict]:
    """Parsea SÓLO las cards de la sección "Programación" de cea.mda.gob.ar —
    las funciones con entrada reservable. Cada card tiene la forma:
        <día>            (número solo)
        <Día> <Mes>      (día de semana completo + mes, ej. "Sábado Julio")
        Ciclo · <ciclo>
        <título>
        <Director> · <Año>
        …  Reservar entrada
    La programación tentativa de más abajo ("Próximamente" / "Vacaciones") NO
    se toma porque todavía no tiene entradas. Devuelve dicts
    {fecha, title, director, year, hora, ciclo}.
    """
    my = re.search(r"\b(" + "|".join(_CEA_MONTHS) + r")\s+(20\d{2})", text, re.IGNORECASE)
    base_year = int(my.group(2)) if my else today.year

    # Horario del ciclo (arriba: "DESDE 18:00 HS · COLÓN 1133 · AVELLANEDA").
    # El innerText llega en MAYÚSCULAS porque el sitio las aplica por CSS y
    # innerText refleja lo renderizado: sin IGNORECASE el "HS" no matcheaba y
    # todas las funciones salían con la hora por defecto en vez de la real.
    default_hora = "19:00"
    hm = re.search(r"(\d{1,2}):(\d{2})\s*hs", text, re.IGNORECASE)
    if hm:
        default_hora = f"{int(hm.group(1)):02d}:{hm.group(2)}"

    wd_month = re.compile(rf"^({_CEA_WD_FULL})\s+(" + "|".join(_CEA_MONTHS) + r")$", re.IGNORECASE)
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    n = len(lines)

    out: list[dict] = []
    seen: set[tuple] = set()
    for i, ln in enumerate(lines):
        if not re.fullmatch(r"\d{1,2}", ln):
            continue
        day = int(ln)
        # La línea siguiente no vacía debe ser "DíaSemana Mes" (card de arriba).
        j = i + 1
        while j < n and not lines[j]:
            j += 1
        if j >= n:
            continue
        m = wd_month.match(lines[j])
        if not m:
            continue
        month = _CEA_MONTHS[m.group(2).lower()]

        # Título / director / año / ciclo dentro de la card. El bloque va desde
        # la línea del día hasta "Director · Año", que lo cierra.
        #
        # El TÍTULO es la ÚLTIMA línea antes de ese cierre; lo que viene antes
        # es el copete del ciclo. Antes se asumía que el copete empezaba con
        # "Ciclo · " y se tomaba la primera línea como título: cuando el CEA
        # cambió el copete a "AVELLANEDA FILMA · Presencia de Diego Lerman"
        # el copete pasó a publicarse COMO título. Tomarlo por posición y no
        # por el prefijo aguanta el próximo rediseño.
        director = ""
        film_year: Optional[int] = None
        rows: list[str] = []
        k = j + 1
        while k < n and k < j + 10:
            row = lines[k]
            if not row:
                k += 1
                continue
            dm = _CEA_DIR_YEAR_RE.match(row)
            if dm:
                director, film_year = dm.group(1).strip(), int(dm.group(2))
                break
            if re.fullmatch(r"\d{1,2}", row):
                break
            rows.append(row)
            k += 1

        title = rows[-1] if rows else ""
        # Ciclo = primer segmento del copete, tanto en el formato viejo
        # ("Ciclo · Radar CEA") como en el nuevo ("RADAR CEA · Clásico
        # restaurado"). _fix_caps en run.py se encarga de las mayúsculas.
        ciclo = ""
        if len(rows) > 1:
            eyebrow = rows[0]
            cm = re.match(r"ciclo\s*·\s*(.+)$", eyebrow, re.IGNORECASE)
            ciclo = (cm.group(1) if cm else eyebrow).split("·")[0].strip()

        # Requerimos "Director · Año": es lo que distingue una card real de
        # arriba de las listas de programación tentativa de más abajo.
        if not (title and director):
            continue
        try:
            d = date(base_year, month, day)
        except ValueError:
            continue
        if d < today - timedelta(days=30):
            try:
                d = date(base_year + 1, month, day)
            except ValueError:
                continue
        if not (today <= d <= cutoff):
            continue
        key = (d.isoformat(), _cea_norm(title))
        if key in seen:
            continue
        seen.add(key)
        out.append({"fecha": d.isoformat(), "title": title, "director": director,
                    "year": film_year, "hora": default_hora, "ciclo": ciclo})
    return out


def _parse_cea_form_blob(blob: str) -> dict:
    """Extrae {day, month, hora} del título/descr de un Google Form de reserva
    del CEA (ej. 'Reserva — … · Viernes 12 Junio · 19:00hs')."""
    out: dict = {}
    tm = re.search(r"(\d{1,2}):(\d{2})\s*hs", blob)
    if tm:
        out["hora"] = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    dm = re.search(r"(\d{1,2})\s+(?:de\s+)?(" + "|".join(_CEA_MONTHS) + r")\b", blob, re.IGNORECASE)
    if dm:
        out["day"] = int(dm.group(1))
        out["month"] = _CEA_MONTHS[dm.group(2).lower()]
    return out


def _cea_form_meta(url: str) -> dict:
    """Lee el título/descr de un Google Form de reserva del CEA para sacar la
    fecha y el horario exactos de la función. Best-effort (urllib)."""
    try:
        soup = fetch_html(url)
    except Exception:
        return {}
    chunks: list[str] = []
    if soup.title:
        chunks.append(soup.title.get_text(" ", strip=True))
    for prop in ("og:title", "og:description"):
        m = soup.find("meta", attrs={"property": prop})
        if m and m.get("content"):
            chunks.append(m["content"])
    return _parse_cea_form_blob(" · ".join(chunks))


async def scrape_cea(page: Page) -> list[Screening]:
    """Scrapea cea.mda.gob.ar (rediseño scroll/SPA) vía playwright + parser de
    texto. El horario exacto de cada función se toma del Google Form de reserva
    (la home lista los horarios del ciclo juntos, sin mapearlos por función)."""
    try:
        await page.goto("https://cea.mda.gob.ar/", wait_until="domcontentloaded", timeout=30000)
        # El sitio es un SPA. Esperar un tiempo fijo alcanzaba en local pero no
        # en el runner de GH Actions, donde la hidratación tarda más: el
        # innerText volvía casi vacío, el parser no encontraba nada y el cine
        # desaparecía de la web sin que fallara ninguna corrida. Esperamos a que
        # aparezca una card de verdad en vez de contar segundos.
        try:
            await page.wait_for_function(
                "() => /reservar\\s+entrada/i.test(document.body.innerText)",
                timeout=25000)
        except Exception:
            pass
        # Sólo necesitamos las cards de arriba (las reservables) + los links a
        # los formularios de reserva; un scroll moderado alcanza.
        for _ in range(8):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(400)
        text = await page.evaluate("document.body.innerText")
        if len(text or "") < 400:
            print(f"[cea: la página rindió {len(text or '')} caracteres — no hidrató]",
                  end=" ", flush=True)
        form_links = await page.eval_on_selector_all(
            'a[href*="docs.google.com/forms"], a[href*="forms.gle"]',
            "els => els.map(e => e.href)",
        )
        # Fallback: en el SPA los links a veces no son <a> simples (botones con
        # JS). Buscamos las URLs de formularios en el HTML renderizado completo.
        html = await page.content()
        form_links = list(form_links or []) + re.findall(
            r'https://(?:docs\.google\.com/forms/[^\s"\'<>\\]+|forms\.gle/[^\s"\'<>\\]+)', html
        )
    except Exception:
        return []

    today = date.today()
    cutoff = today + timedelta(days=60)

    # Horario exacto por función: leemos cada Google Form de reserva (dedup) y
    # lo asociamos a la función por fecha (cada función es un día distinto).
    form_by_date: dict[tuple[int, int], dict] = {}
    for url in dict.fromkeys(form_links or []):
        meta = _cea_form_meta(url)
        if "day" in meta and "month" in meta:
            form_by_date[(meta["month"], meta["day"])] = {"hora": meta.get("hora"), "url": url}

    result: list[Screening] = []
    for ev in _parse_cea_text(text, today, cutoff):
        _, mo, d = (int(x) for x in ev["fecha"].split("-"))
        form = form_by_date.get((mo, d), {})
        result.append(Screening(
            cine="CEA",
            title=ev["title"],
            fecha=ev["fecha"],
            hora=form.get("hora") or ev["hora"],
            ticket_url=form.get("url") or "https://cea.mda.gob.ar/",
            director=ev["director"],
            year=ev["year"],
            ciclo=ev.get("ciclo", ""),
        ))
    return result


# ---------------------------------------------------------------------------
# Filo Cine — Microcine de la Facultad de Filosofía y Letras (UBA)
# filo.uba.ar/cines-en-filo — listado HTML estático (Drupal), detalle por film
# con director, país, año y duración.
# ---------------------------------------------------------------------------

FILO_BASE = "https://www.filo.uba.ar"


def _fetch_filo_film_meta(url: str) -> dict:
    """
    Extrae {director, country, year, duration, ciclo} desde la página de
    detalle de una película de Filo Cine. La ficha técnica está renderizada
    como un <p> por campo (ej. "Director: ...", "Duración : 56 min").
    """
    try:
        soup = fetch_html(url)
    except Exception:
        return {}

    out: dict = {}
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if len(txt) > 300:
            continue
        m = re.match(r"^Director(?:a|es|as)?\s*:\s*(.+)$", txt, re.I)
        if m and "director" not in out:
            out["director"] = m.group(1).strip().rstrip(".")
            continue
        m = re.match(r"^Duración\s*:?\s*(\d{1,3})", txt, re.I)
        if m:
            out["duration"] = int(m.group(1))
            continue
        m = re.match(r"^País\s*(?:y\s+año)?\s*(?:de\s+producción)?\s*:?\s*(.+)$", txt, re.I)
        if m:
            rest = m.group(1)
            ym = re.search(r"(19\d{2}|20\d{2})", rest)
            if ym:
                out["year"] = int(ym.group(1))
            country = re.sub(r"[,\-–·•]?\s*(19\d{2}|20\d{2}).*$", "", rest).strip().rstrip(",").strip()
            if country:
                out["country"] = country
            continue
        m = re.match(r"^Año\s*(?:de\s+producción)?\s*:?\s*(\d{4})", txt, re.I)
        if m and "year" not in out:
            out["year"] = int(m.group(1))
            continue
        m = re.match(r"^Género\s*:?\s*(.+)$", txt, re.I)
        if m:
            out["ciclo"] = m.group(1).strip().rstrip(".")
            continue

    return out


def scrape_filo() -> list[Screening]:
    """
    Scrapea filo.uba.ar/cines-en-filo. El listado tiene un .left-agenda-grid
    por función con día, mes corto en español, título (link al detalle),
    horario, sede ("Microcine") y categoría.

    La página NO trae el año: lo inferimos asumiendo "más cercano en el futuro"
    (si el día/mes ya pasó este año, es del siguiente).
    """
    try:
        soup = fetch_html(f"{FILO_BASE}/cines-en-filo")
    except Exception:
        return []

    today = date.today()
    cutoff = today + timedelta(days=120)
    result: list[Screening] = []
    meta_cache: dict[str, dict] = {}

    for row in soup.select(".left-agenda-grid.agenda-grid"):
        day_el = row.select_one(".agenda-day")
        month_el = row.select_one(".agenda-month")
        title_link = row.select_one(".card-title a")
        if not (day_el and month_el and title_link):
            continue

        try:
            day_num = int(re.sub(r"\D", "", day_el.get_text(strip=True)))
        except ValueError:
            continue

        month_text = month_el.get_text(strip=True).lower().rstrip(".")
        month = MESES_ES.get(month_text)
        if not month:
            # Probar prefijos más largos / cortos
            for k, v in MESES_ES.items():
                if month_text.startswith(k) or k.startswith(month_text):
                    month = v
                    break
        if not month:
            continue

        # Año: el más cercano que no sea pasado
        year = today.year
        try:
            d = date(year, month, day_num)
        except ValueError:
            continue
        if d < today:
            try:
                d = date(year + 1, month, day_num)
            except ValueError:
                continue
        if d > cutoff:
            continue

        title = title_link.get_text(" ", strip=True)
        href = title_link.get("href", "")
        detail_url = href if href.startswith("http") else f"{FILO_BASE}{href}"

        # Horario: primer .event-info con la imagen clock.png
        hora = ""
        for info in row.select(".event-info"):
            img = info.find("img")
            if img and "clock" in (img.get("src") or "").lower():
                hm = re.search(r"(\d{1,2}):(\d{2})", info.get_text(" ", strip=True))
                if hm:
                    hora = f"{int(hm.group(1)):02d}:{hm.group(2)}"
                break
        if not hora:
            continue

        # Categoría (Ficción / Documental) — la usamos como ciclo si no hay
        # género más específico en el detalle.
        cat_el = row.select_one(".event-category")
        categoria = cat_el.get_text(" ", strip=True) if cat_el else ""

        # Enriquecer con metadata del detalle (director / país / año / duración)
        if detail_url not in meta_cache:
            meta_cache[detail_url] = _fetch_filo_film_meta(detail_url)
        meta = meta_cache[detail_url]

        result.append(Screening(
            cine="Filo Cine",
            title=title,
            fecha=d.isoformat(),
            hora=hora,
            ticket_url=detail_url,
            ciclo=meta.get("ciclo") or categoria,
            director=meta.get("director", ""),
            country=meta.get("country", ""),
            year=meta.get("year"),
            duration=meta.get("duration"),
        ))

    return result


# ---------------------------------------------------------------------------
# Biblioteca Nacional — Auditorio Jorge Luis Borges
# bn.gov.ar/agenda-cultural?categoria=cine lista los ciclos de cine. Cada evento
# tiene un bloque "Programación"/"Programa" con un patrón que se repite por
# función:
#     <p><b>{Día} {n} de {mes} | {hora} hs.</b></p>     ← fecha + horario
#     <p>[prefijo de] <i>Título</i> de Director (Año)</p> ← película
# El parser detecta cada línea de fecha y toma el <p> siguiente como película.
# El título sale del <i>/<em> si existe; si no, del texto: se saca el prefijo
# ("Preestreno de", "Función especial de"...) y se corta por el último " de "
# (que separa título de director, incluso cuando el título lleva " de ").
# ---------------------------------------------------------------------------

BN_BASE = "https://www.bn.gov.ar"
BN_INDEX = "https://www.bn.gov.ar/agenda-cultural?categoria=cine"

_BN_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_BN_DATE_RE = re.compile(
    r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo)?\s*"
    r"(\d{1,2})\s+de\s+(" + "|".join(_BN_MESES) + r")\s*\|\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*h", re.IGNORECASE)
_BN_PREFIX_RE = re.compile(
    r"^\s*(?:preestreno|funci[oó]n\s+especial|funci[oó]n|proyecci[oó]n|"
    r"estreno|presentaci[oó]n|charla)\s+(?:de|del)\s+", re.IGNORECASE)


def _bn_event_range(soup) -> "Optional[tuple[date, date]]":
    """Rango de fechas del evento (DD/MM/YY - DD/MM/YY) → para resolver el año."""
    ds = re.findall(r"(\d{2})/(\d{2})/(\d{2})", soup.get_text(" ", strip=True))
    dts = []
    for dd, mm, yy in ds[:2]:
        try:
            dts.append(date(2000 + int(yy), int(mm), int(dd)))
        except ValueError:
            pass
    return (min(dts), max(dts)) if dts else None


def _bn_resolve_year(day: int, month: int, rng) -> int:
    if rng:
        start, end = rng
        for y in {start.year, end.year}:
            try:
                d = date(y, month, day)
            except ValueError:
                continue
            if start <= d <= end:
                return y
    today = date.today()
    return today.year + 1 if month < today.month else today.year


_BN_GENERICO_RE = re.compile(
    r"^(?:proyecci[óo]n|funci[óo]n|presentaci[óo]n|charla|cine|estreno|encuentro)$",
    re.IGNORECASE)


def _bn_parse_film(text: str, italic: str) -> "tuple[str, str, Optional[int]]":
    text = re.sub(r"\s+", " ", text).strip()
    year = None
    ym = re.search(r"\((\d{4})\)", text)
    if ym:
        year = int(ym.group(1))
    director = ""
    if italic and italic.strip(" .,"):
        title = italic.strip(" .,")
        after = text.split(title, 1)[-1] if title in text else text
        dm = re.search(r"\bde\s+(.+)", after, re.IGNORECASE)
        if dm:
            director = re.sub(r"\(\d{4}\).*", "", dm.group(1)).strip(" .,")
    else:
        t = _BN_PREFIX_RE.sub("", text)
        t = re.sub(r"\(\d{4}\).*", "", t).strip(" .,")
        parts = re.split(r"\s+de\s+", t)
        if len(parts) >= 2:
            director = parts[-1].strip(" .,")
            title = " de ".join(parts[:-1]).strip(" .,")
        else:
            title = t.strip(" .,")

    # "Proyección de Invasión de Hugo Santiago. Charla con especialistas": la BN
    # a veces pone una etiqueta genérica donde va el título y mete la película
    # adentro del "de …". Sin esto la cartelera publica una función que se
    # llama "Proyección" y un director que es media oración.
    if title and _BN_GENERICO_RE.match(title.strip(" .,")) and director:
        resto = re.split(r"[.;]", director, 1)[0].strip()
        partes = re.split(r"\s+de\s+", resto)
        if len(partes) >= 2:
            # El último "de" separa director de título ("Invasión de los
            # ultracuerpos de Philip Kaufman" → título / director).
            title = " de ".join(partes[:-1]).strip(" .,")
            director = partes[-1].strip(" .,")
        elif resto:
            title, director = resto, ""
    return title, director, year


def _bn_parse_event(soup, ciclo: str, ticket_url: str) -> list[Screening]:
    rng = _bn_event_range(soup)
    # Párrafos "hoja" (sin <p> anidado), en orden de aparición.
    ps = [p for p in soup.find_all("p") if not p.find("p")]
    today = date.today()
    out: list[Screening] = []
    seen: set[tuple] = set()

    for i, p in enumerate(ps):
        m = _BN_DATE_RE.search(p.get_text(" ", strip=True))
        if not m:
            continue
        day, month = int(m.group(1)), _BN_MESES[m.group(2).lower()]
        hora = f"{int(m.group(3)):02d}:{int(m.group(4) or 0):02d}"

        # La película es el siguiente <p> no vacío que no sea otra fecha.
        film_p = None
        for q in ps[i + 1:]:
            qt = q.get_text(" ", strip=True)
            if not qt:
                continue
            if _BN_DATE_RE.search(qt):
                break
            film_p = q
            break
        if film_p is None:
            continue

        it = film_p.find(["i", "em"])
        title, director, year = _bn_parse_film(
            film_p.get_text(" ", strip=True),
            it.get_text(" ", strip=True) if it else "")
        if not title or len(title) < 2:
            continue

        try:
            d = date(_bn_resolve_year(day, month, rng), month, day)
        except ValueError:
            continue
        if d < today:
            continue

        key = (title, d.isoformat(), hora)
        if key in seen:
            continue
        seen.add(key)
        out.append(Screening(
            cine="Biblioteca Nacional",
            title=title,
            fecha=d.isoformat(),
            hora=hora,
            ticket_url=ticket_url,
            ciclo=ciclo,
            director=director,
            country="",
            year=year,
        ))
    return out


def scrape_bn() -> list[Screening]:
    """
    Scrapea los ciclos de cine de la Biblioteca Nacional. Descubre los eventos
    desde bn.gov.ar/agenda-cultural?categoria=cine y parsea el bloque de
    programación de cada uno (ver patrón en el comentario de arriba).
    """
    try:
        idx = fetch_html(BN_INDEX)
    except Exception:
        return []

    event_urls: list[str] = []
    seen: set[str] = set()
    for a in idx.find_all("a", href=re.compile(r"/agenda-cultural/[^?#]")):
        h = a["href"]
        u = h if h.startswith("http") else BN_BASE + ("" if h.startswith("/") else "/") + h
        if u not in seen:
            seen.add(u)
            event_urls.append(u)

    result: list[Screening] = []
    for url in event_urls:
        try:
            soup = fetch_html(url)
        except Exception:
            continue
        og = soup.find("meta", property="og:title")
        ciclo = (og["content"].strip() if og and og.get("content") else "")
        result.extend(_bn_parse_event(soup, ciclo, url))
    return result


# ---------------------------------------------------------------------------
# Centro Cultural de la Cooperación  (centrocultural.coop — Drupal)
# ---------------------------------------------------------------------------
# La cartelera de cine vive en /cartelera-mes/1436/YYYY-MM (1436 = categoría
# "Cine", estable entre meses). Cada evento trae una línea de fecha en
# lenguaje natural; los formatos vistos:
#   "Martes 2 y 9 de Junio 19:00"                  → días sueltos
#   "Miércoles de Junio 20:00"                     → todos los miércoles del mes
#   "Funciones: Miércoles de Marzo y Abril 20:30"  → recurrente en varios meses

CCD_BASE = "https://www.centrocultural.coop"
CCD_CINE_CAT = 1436

_CCD_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_CCD_DIAS = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}
_CCD_MES_RE = re.compile(r"\b(" + "|".join(_CCD_MESES) + r")\b", re.IGNORECASE)
_CCD_DIA_RE = re.compile(r"\b(" + "|".join(_CCD_DIAS) + r")s?\b", re.IGNORECASE)


def _ccd_month_urls(meses: int) -> list[tuple[str, int]]:
    """URLs de cartelera (mes actual + próximos) junto al año de referencia."""
    today = date.today()
    out: list[tuple[str, int]] = []
    y, m = today.year, today.month
    for _ in range(max(1, meses)):
        out.append((f"{CCD_BASE}/cartelera-mes/{CCD_CINE_CAT}/{y:04d}-{m:02d}", y))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _ccd_month_year(base_year: int, month: int, today: date) -> int:
    """Resuelve el año real de un mes nombrado (cruce diciembre→enero)."""
    if date(base_year, month, 28) < today - timedelta(days=40):
        return base_year + 1
    return base_year


def _ccd_expand_fecha(fecha_text: str, base_year: int,
                      today: date) -> list[tuple[str, str]]:
    """Expande la línea de fecha en lenguaje natural a [(YYYY-MM-DD, HH:MM)]."""
    tm = re.search(r"\b(\d{1,2})[:.](\d{2})\b", fecha_text)
    if not tm:
        return []
    hora = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    # Quitamos la hora para no confundir sus dígitos con números de día.
    body = fecha_text[:tm.start()] + fecha_text[tm.end():]

    months = [_CCD_MESES[m.group(1).lower()] for m in _CCD_MES_RE.finditer(body)]
    days = [int(n) for n in re.findall(r"\b(\d{1,2})\b", body) if 1 <= int(n) <= 31]
    dm = _CCD_DIA_RE.search(body)
    weekday = _CCD_DIAS[dm.group(1).lower()] if dm else None

    out: list[tuple[str, str]] = []
    if days:
        # Días sueltos: "Martes 2 y 9 de Junio 19:00".
        if not months:
            return []
        month = months[0]
        yr = _ccd_month_year(base_year, month, today)
        for day in days:
            try:
                d = date(yr, month, day)
            except ValueError:
                continue
            out.append((d.isoformat(), hora))
    elif weekday is not None and months:
        # Recurrente: "Miércoles de Junio 20:00" → todos los miércoles del mes.
        for month in months:
            yr = _ccd_month_year(base_year, month, today)
            d = date(yr, month, 1)
            while d.month == month:
                if d.weekday() == weekday:
                    out.append((d.isoformat(), hora))
                d += timedelta(days=1)
    return out


def _ccd_meta(desc: str) -> tuple[str, Optional[int]]:
    """Extrae (director, duración_min) de la meta-descripción del evento."""
    director = ""
    m = re.search(r"(?:Gui[oó]n y direcci[oó]n|Direcci[oó]n|Dirige)\s*:?\s*"
                  r"([^\n.]+)", desc, re.IGNORECASE)
    if m:
        director = re.split(
            r"\b(?:Duraci|Elenco|G[eé]nero|Guion|Pa[ií]s|A[ñn]o|Productor|Reparto)",
            m.group(1))[0].strip(" .,")
    else:
        m = re.match(r"\s*De\s+(.+?)\.", desc)
        if m:
            director = m.group(1).strip(" .,")
    dm = re.search(r"(\d{1,3})\s*minutos", desc, re.IGNORECASE)
    duration = int(dm.group(1)) if dm else None
    return director, duration


def scrape_ccd(meses: int = 3) -> list[Screening]:
    """
    Scrapea la cartelera de cine del Centro Cultural de la Cooperación.
    Recorre el mes actual y los próximos (`meses`), expandiendo la línea de
    fecha en lenguaje natural de cada evento a funciones concretas.
    """
    today = date.today()
    result: list[Screening] = []
    seen: set[tuple] = set()
    meta_cache: dict[str, tuple[str, Optional[int]]] = {}

    for url, year in _ccd_month_urls(meses):
        try:
            soup = fetch_html(url)
        except Exception:
            continue

        for div in soup.find_all("div", class_="info-evento"):
            a = div.find("a", href=re.compile(r"/eventos/"))
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            ev_url = href if href.startswith("http") else CCD_BASE + href

            # La línea de fecha es el nodo de texto suelto dentro de info-evento
            # ("Martes 2 y 9 de Junio 19:00"). Fallback: el span dd/mm/aaaa.
            fecha_text = " ".join(
                t.strip() for t in div.find_all(string=True, recursive=False)
                if t.strip())
            if not fecha_text:
                sp = div.find("span", class_="date-display-single")
                fecha_text = sp.get_text(strip=True) if sp else ""

            dates = _ccd_expand_fecha(fecha_text, year, today)
            if not dates:
                continue

            if ev_url not in meta_cache:
                director, duration = "", None
                try:
                    dsoup = fetch_html(ev_url)
                    dm = dsoup.find("meta", attrs={"name": "description"})
                    if dm and dm.get("content"):
                        director, duration = _ccd_meta(dm["content"])
                except Exception:
                    pass
                meta_cache[ev_url] = (director, duration)
            director, duration = meta_cache[ev_url]

            for fecha, hora in dates:
                if fecha < today.isoformat():
                    continue
                key = (title, fecha, hora)
                if key in seen:
                    continue
                seen.add(key)
                result.append(Screening(
                    cine="Centro Cultural de la Cooperación",
                    title=title,
                    fecha=fecha,
                    hora=hora,
                    ticket_url=ev_url,
                    director=director,
                    duration=duration,
                ))
    return result


# ---------------------------------------------------------------------------
# Casa Nacional del Bicentenario  (casadelbicentenario.cultura.gob.ar)
# ---------------------------------------------------------------------------
# Las actividades de cine están taggeadas con badge "Cine" en /actividades/.
# Cada actividad es un ciclo cuyo cuerpo lista una función por fecha, p. ej.:
#   "Domingo 7. 19HS Muña Muña (2025) Dur. 67 min. Guion y dirección: ..."
#   "Domingo 5 de julio, 19HS Cinéfilos (2024) Dir. Arnaud Desplechin. 88 min"
# El mes/año se toma del bloque "Cuándo" (rango de fechas) y la hora del
# bloque "Horario" si la línea de función no la trae.

CB_BASE = "https://casadelbicentenario.cultura.gob.ar"
CB_LISTING = CB_BASE + "/actividades/"

_CB_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
# El sitio escribe los meses completos ("2 agosto 2026") o abreviados con
# punto ("2 Ago. 2026"). Aceptamos ambos y resolvemos por prefijo.
_CB_MES_RE = r"[a-záéíóúñ]{3,10}\.?"


def _cb_mes_num(token: str) -> "Optional[int]":
    t = token.strip().rstrip(".").lower()
    for name, num in _CB_MESES.items():
        if name.startswith(t) or t.startswith(name[:3]):
            return num
    return None


_CB_DOW = r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo"
# Formatos de fecha vistos en las fichas:
#   "Domingo 7. 19HS"            → día suelto (el mes sale del rango "Cuándo")
#   "Domingo 5 de julio, 19HS"   → día + mes en palabras
#   "Domingo 2/8. 19HS"          → día/mes numérico
_CB_FUNC_RE = re.compile(
    r"(?:^|\b)(?:" + _CB_DOW + r")\s+(\d{1,2})"
    r"(?:\s*/\s*(\d{1,2})|\s+de\s+(" + _CB_MES_RE + r"))?"
    r"[.,:]?\s*(?:(\d{1,2})(?::(\d{2}))?\s*HS\b)?",
    re.IGNORECASE)
_CB_RANGE_RE = re.compile(
    r"(\d{1,2})\s+(" + _CB_MES_RE + r")\s+(\d{4})", re.IGNORECASE)
# La primera función del ciclo suele venir precedida por el rótulo de la
# sección, que rompe el ancla de inicio de línea.
_CB_PREFIX_RE = re.compile(
    r"^\s*(?:PROGRAMACI[ÓO]N|PROGRAMA|FUNCIONES)\s*[:.\-]?\s*", re.IGNORECASE)
# Funciones dadas de baja — no las publicamos.
_CB_CANCEL_RE = re.compile(r"\b(?:SUSPENDID|CANCELAD|REPROGRAMAD)", re.IGNORECASE)


def _cb_section(soup, label: str) -> str:
    """Texto de una sección del sidebar (Cuándo / Horario / Entrada)."""
    for h in soup.find_all(["h4", "h3"]):
        if h.get_text(strip=True).lower() == label:
            parts = []
            for sib in h.next_siblings:
                if getattr(sib, "name", None) in ("h4", "h3"):
                    break
                t = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else ""
                if t:
                    parts.append(t)
            return " ".join(parts)
    return ""


def _cb_cuando(soup) -> "tuple[Optional[date], Optional[date]]":
    txt = _cb_section(soup, "cuándo")
    ds = []
    for d, mes, y in _CB_RANGE_RE.findall(txt):
        num = _cb_mes_num(mes)
        if not num:
            continue
        try:
            ds.append(date(int(y), num, int(d)))
        except ValueError:
            pass
    return (min(ds), max(ds)) if ds else (None, None)


def _cb_horario(soup) -> str:
    m = re.search(r"(\d{1,2}):(\d{2})", _cb_section(soup, "horario"))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else "19:00"


def _cb_resolve_date(day: int, month: int, start: "Optional[date]",
                     end: "Optional[date]") -> "Optional[date]":
    years = {start.year, end.year} if start and end else (
        {start.year} if start else {date.today().year})
    for y in years:
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if start and end and start - timedelta(days=3) <= d <= end + timedelta(days=3):
            return d
    try:
        return date(min(years), month, day)
    except ValueError:
        return None


def _cb_parse_film(rest: str) -> "tuple[str, Optional[int], str, Optional[int], str]":
    """De la cola de una función saca (título, año, director, duración, original).

    Las fichas traen la metadata entre paréntesis después del título, en
    variantes como:
        "Escenas en el mar (1991, 101m. Dir. Takeshi Kitano) *(Ano Natsu…)"
        "La tumba de las luciérnagas (animación, 1988, 88m. Dir. Isao Takahata)"
        "Cinéfilos (2024) Dir. Arnaud Desplechin. 88 min"
    """
    rest = re.sub(r"^(PRE\s*ESTRENO|ESTRENO|FUNCI[ÓO]N\s+ESPECIAL)[\s:.\-]*",
                  "", rest, flags=re.IGNORECASE).strip()
    # El título es todo lo anterior al bloque de metadata (primer paréntesis
    # o el primer marcador Dir./Dur.).
    cut = re.search(r"\s*\(|\s+(?:Dir\b|Direcci|Guion|Dur\.)", rest, re.IGNORECASE)
    title = (rest[:cut.start()] if cut else rest).strip(" .,:–-")
    # El año puede no estar solo entre paréntesis: lo buscamos en la metadata.
    ym = re.search(r"\b(?:19|20)\d{2}\b", rest[cut.start():] if cut else "")
    year = int(ym.group(0)) if ym else None
    director = ""
    dm = re.search(r"(?:Guion y direcci[oó]n|Direcci[oó]n|Dir)\.?\s*:?\s*([^.()\n]+)",
                   rest, re.IGNORECASE)
    if dm:
        cand = re.split(r"\b\d+\s*min", dm.group(1))[0].strip(" .,")
        # Sin delimitador claro la sinopsis se pega al nombre: si es largo, lo
        # dejamos vacío y que Letterboxd complete el director.
        if len(cand) <= 40 and len(cand.split()) <= 5:
            director = cand
    # Duración: "88 min", "124min", "101m."
    durm = re.search(r"(\d{1,3})\s*(?:m\b|min\b|minutos\b)", rest, re.IGNORECASE)
    duration = int(durm.group(1)) if durm else None
    # Título original: el sitio lo marca con asterisco, "*(Hotaru no Haka)"
    # o "(*Osaka Monogatari)". Sirve de hint para el match en Letterboxd.
    om = re.search(r"\*\s*\(([^)]+)\)|\(\s*\*([^)]+)\)", rest)
    original = (om.group(1) or om.group(2)).strip() if om else ""
    return title, year, director, duration, original


def _cb_parse_detail(soup, url: str) -> list[Screening]:
    h1 = soup.find(["h1", "h2"])
    title_full = h1.get_text(" ", strip=True) if h1 else ""
    ciclo = title_full.split("|", 1)[1].strip() if "|" in title_full else title_full
    start, end = _cb_cuando(soup)
    hora_default = _cb_horario(soup)
    art = soup.find("div", class_="article") or soup

    blocks: list[str] = []
    for p in art.find_all(["p", "li"]):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        if t:
            blocks.append(t)

    out: list[Screening] = []
    seen: set[tuple] = set()
    for i, raw in enumerate(blocks):
        t = _CB_PREFIX_RE.sub("", raw)
        # La fecha puede no estar al principio del bloque (rótulos, negritas
        # partidas); exigimos que aparezca cerca del inicio para no capturar
        # fechas sueltas dentro de una sinopsis.
        m = _CB_FUNC_RE.search(t)
        if not m or m.start() > 40:
            continue
        day = int(m.group(1))
        if m.group(2):                                    # "2/8"
            month = int(m.group(2))
        elif m.group(3):                                  # "2 de agosto"
            month = _cb_mes_num(m.group(3))
        else:                                             # sólo el día
            month = start.month if start else None
        if not month or not 1 <= month <= 12:
            continue
        hora = (f"{int(m.group(4)):02d}:{int(m.group(5) or 0):02d}"
                if m.group(4) else hora_default)
        rest = t[m.end():].strip()
        # Cuando la fecha viene sola en su párrafo, la película está en el
        # bloque siguiente.
        if len(rest) < 3 and i + 1 < len(blocks):
            rest = blocks[i + 1]
        if _CB_CANCEL_RE.search(rest):
            continue
        title, year, director, duration, original = _cb_parse_film(rest)
        if not title or len(title) < 2:
            continue
        # Las fichas también traen fechas dentro del párrafo introductorio
        # ("El sábado 8 de agosto a las 19, la Casa recibe al Festival…"), y
        # de ahí salían títulos que en realidad son prosa. Una función real
        # siempre declara al menos año, dirección o duración.
        if not (year or director or duration):
            continue
        # Algunas fichas describen el programa en prosa bajo una fecha real
        # ("Jueves 21 de mayo. 19HS Los filmes que componen este programa…").
        # Ningún título de película llega a esa extensión.
        if len(title) > 55:
            continue
        d = _cb_resolve_date(day, month, start, end)
        if not d:
            continue
        key = (title, d.isoformat(), hora)
        if key in seen:
            continue
        seen.add(key)
        out.append(Screening(
            cine="Casa del Bicentenario",
            title=title,
            fecha=d.isoformat(),
            hora=hora,
            ticket_url=url,
            ciclo=ciclo,
            director=director,
            year=year,
            duration=duration,
            original_title=original,
        ))

    # Fallback: actividad de cine sin líneas de función parseables → 1 función
    # en la fecha de inicio, con el título del ciclo.
    if not out and start:
        out.append(Screening(
            cine="Casa del Bicentenario",
            title=ciclo,
            fecha=start.isoformat(),
            hora=hora_default,
            ticket_url=url,
            ciclo="",
        ))
    return out


def _cb_cine_urls(max_pages: int = 3) -> list[str]:
    """Descubre URLs de actividades con badge 'Cine' desde /actividades/."""
    urls: list[str] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        u = CB_LISTING if page == 1 else f"{CB_LISTING}?page={page}"
        try:
            soup = fetch_html(u)
        except Exception as e:
            # Silenciar esto hacía que el runner reportara "0 funciones" sin
            # causa, indistinguible de "no hay cine programado".
            print(f"[CB] falló el listado {u}: {e}", flush=True)
            break
        cards = soup.select("div.agenda div.card")
        if not cards:
            if page == 1:
                print(f"[CB] el listado no devolvió tarjetas — ¿cambió el "
                      f"markup o nos bloquearon? ({u})", flush=True)
            break
        for card in cards:
            badge = card.find("span", class_="badge")
            if not badge or badge.get_text(strip=True).lower() != "cine":
                continue
            a = (card.select_one("h4.card-title a[href]")
                 or card.find("a", href=re.compile(r"/actividad/")))
            if not a:
                continue
            href = a["href"]
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = CB_BASE + href
            href = href.split("?")[0]
            if href not in seen:
                seen.add(href)
                urls.append(href)
    return urls


CB_MANUAL_PATH = Path(__file__).parent / "data" / "cb_manual.json"


def _cb_manual(today: date) -> list[Screening]:
    """Override manual (data/cb_manual.json). Se mergea con el scrape y se
    filtra a partir de hoy, así que las funciones pasadas se caen solas."""
    if not CB_MANUAL_PATH.exists():
        return []
    try:
        data = json.loads(CB_MANUAL_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[CB] override manual ilegible: {e}", flush=True)
        return []
    out: list[Screening] = []
    for s in data.get("screenings", []):
        title = (s.get("title") or "").strip()
        try:
            d = date.fromisoformat(s["fecha"])
        except (KeyError, ValueError):
            continue
        if not title or d < today:
            continue
        out.append(Screening(
            cine="Casa del Bicentenario", title=title,
            fecha=s["fecha"], hora=s.get("hora", "19:00"),
            ticket_url=s.get("ticket_url", CB_LISTING), ciclo=s.get("ciclo", ""),
            director=s.get("director", ""), year=s.get("year"),
            duration=s.get("duration"), original_title=s.get("original_title", ""),
        ))
    return out


def scrape_cb(max_pages: int = 3) -> list[Screening]:
    """
    Scrapea la cartelera de cine de la Casa Nacional del Bicentenario.
    Descubre las actividades de cine y parsea cada ciclo en funciones
    individuales (una película por fecha).

    Se mergea con data/cb_manual.json (dedup por título+fecha+hora): el sitio
    responde distinto desde los runners de GitHub que desde una IP local, así
    que el override es la red de contención cuando el listado viene vacío.
    """
    today = date.today()
    result: list[Screening] = []
    seen: set[tuple] = set()
    for url in _cb_cine_urls(max_pages):
        try:
            soup = fetch_html(url)
        except Exception:
            continue
        for s in _cb_parse_detail(soup, url):
            if s.fecha < today.isoformat():
                continue
            key = (s.title, s.fecha, s.hora)
            if key in seen:
                continue
            seen.add(key)
            result.append(s)

    manual = _cb_manual(today)
    added = 0
    for s in manual:
        key = (s.title, s.fecha, s.hora)
        if key in seen:
            continue
        seen.add(key)
        result.append(s)
        added += 1
    if added:
        print(f"[CB] +{added} función(es) desde el override manual", flush=True)
    return result


# ---------------------------------------------------------------------------
# Biblioteca del Congreso — Auditorio Leonardo Favio  (bcn.gob.ar)
# ---------------------------------------------------------------------------
# bcn.gob.ar/agenda/cine lista una card por función (martes y jueves, 18:30).
# Cada card trae:
#     <h3 class="titulo_padre">Ciclo de cine: {ciclo}</h3>
#     <h2 class="titulo_miniatura">{Título español} ({Título original})</h2>
#     <div class="descripcion_corta">{Director}, {Año}, {Duración}’</div>
#     ... "2 de julio" + "18:30 h"
# La card no dice el año, así que abrimos la página de detalle, que trae la
# fecha completa (DD/MM/YYYY), la ficha técnica y el link de reserva
# (Eventbrite). Si el detalle falla, se cae a la card y se infiere el año.
# ---------------------------------------------------------------------------

BCN_BASE = "https://bcn.gob.ar"
BCN_AGENDA = "https://bcn.gob.ar/agenda/cine"

_BCN_CICLO_RE = re.compile(r"^\s*ciclo\s*(?:de\s*cine)?\s*:\s*", re.IGNORECASE)
_BCN_FICHA_RE = {
    "director": re.compile(r"Direcci[oó]n\s*:\s*([^\n]+)"),
    "country": re.compile(r"Pa[ií]s(?:es)?\s*:\s*([^\n]+)"),
    "year": re.compile(r"A[ñn]o\s*:\s*(\d{4})"),
    "duration": re.compile(r"Duraci[oó]n\s*:\s*(\d{1,3})"),
}


def _bcn_split_title(raw: str) -> "tuple[str, str]":
    """
    "Perfectos desconocidos (Perfetti sconosciuti)" → título + título original.
    Solo separa si el paréntesis final parece un título (no un año ni "1ª parte").
    """
    t = re.sub(r"\s+", " ", raw).strip()
    m = re.search(r"^(.+?)\s*\(([^()]+)\)\s*$", t)
    if not m:
        return t, ""
    title, paren = m.group(1).strip(" .,"), m.group(2).strip(" .,")
    if not title or len(paren) < 2 or re.fullmatch(r"[\d\s\-–/]+", paren):
        return t, ""
    if re.search(r"\b(parte|temporada|episodio|versi[oó]n|copia|restaurad)", paren, re.IGNORECASE):
        return t, ""
    return title, paren


def _bcn_parse_ficha(text: str) -> dict:
    """Ficha técnica de la página de detalle: Dirección / Año / Duración / País."""
    out: dict = {}
    for key, rx in _BCN_FICHA_RE.items():
        m = rx.search(text)
        if not m:
            continue
        val = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
        if key == "director":
            # Algunas fichas van todas en un renglón ("Dirección: Hugo Santiago.
            # 1969. 123´"): cortamos donde arranca el año/duración para no
            # publicar un director con la ficha entera pegada.
            val = re.split(r"[.,;]\s*(?=\d)", val)[0].strip(" .,;")
        if not val:
            continue
        out[key] = int(val) if key in ("year", "duration") else val
    return out


def _bcn_parse_corta(text: str) -> dict:
    """De "Steven Spielberg, 1987, 152’" saca director / año / duración."""
    out: dict = {}
    t = re.sub(r"\s+", " ", text).strip(" .,")
    if not t:
        return out
    # El director es lo que va antes del año. El separador es coma
    # ("Steven Spielberg, 1987, 152’") o punto ("Hugo Santiago. 1969. 123´"):
    # cortar sólo por coma dejaba la ficha entera como nombre del director.
    cabeza = re.split(r"[.,;]\s*(?=\d)", t)[0].strip(" .,")
    if cabeza and not re.fullmatch(r"[\d\s’'´`\-–]+", cabeza):
        out["director"] = cabeza
    ym = re.search(r"\b(19|20)\d{2}\b", t)
    if ym:
        out["year"] = int(ym.group(0))
    dm = re.search(r"\b(\d{2,3})\s*[’'´`]", t)
    if dm:
        out["duration"] = int(dm.group(1))
    return out


# Cronograma de un ciclo/festival de la BCN. La agenda muestra una card por
# FECHA con un título de relleno ("Proyección de 'Collateral' y 'Aqui nao entra
# luz'") y la bajada institucional donde debería ir el director; las películas
# de verdad, con ficha técnica, están en el bloque "Cronograma" de la página del
# ciclo, con esta forma:
#
#     calendar_clock
#     Martes 18 de agosto -
#     18.30 h
#     Cortometraje:
#     The Fortunate
#     Dirección: Habtamu Gebrehiwot,
#     Año: 2026
#     Duración: 15´
#
# Cuando la página tiene cronograma, cada película es una función propia y las
# cards de la agenda se ignoran.
_BCN_CRONO_DIA_RE = re.compile(
    r"^(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\s+"
    r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)", re.IGNORECASE)
_BCN_CRONO_HORA_RE = re.compile(r"^(\d{1,2})[.:](\d{2})\s*h?\b")
_BCN_CRONO_FILM_RE = re.compile(
    r"^(?:corto|largo)metraje\s*:\s*(.*)$", re.IGNORECASE)


def _bcn_cronograma(soup, ciclo: str, ticket_url: str,
                    today: date) -> list[Screening]:
    """Una Screening por película del bloque "Cronograma". [] si no hay."""
    lines = [re.sub(r"[ \t]+", " ", l).strip()
             for l in soup.get_text("\n").splitlines()]
    lines = [l for l in lines if l]
    try:
        inicio = next(i for i, l in enumerate(lines) if l.lower() == "cronograma")
    except StopIteration:
        return []

    out: list[Screening] = []
    d: Optional[date] = None
    hora = "18:30"
    i = inicio + 1
    while i < len(lines):
        ln = lines[i]

        md = _BCN_CRONO_DIA_RE.match(ln)
        if md:
            mes = MESES_ES.get(md.group(2).lower())
            if mes:
                dia = int(md.group(1))
                # La agenda sólo publica funciones futuras: si el mes ya pasó,
                # es del año que viene.
                anio = today.year + 1 if mes < today.month else today.year
                try:
                    d = date(anio, mes, dia)
                except ValueError:
                    d = None
            # La hora va en la línea siguiente ("18.30 h").
            for j in range(i + 1, min(i + 3, len(lines))):
                mh = _BCN_CRONO_HORA_RE.match(lines[j])
                if mh:
                    hora = f"{int(mh.group(1)):02d}:{mh.group(2)}"
                    break
            i += 1
            continue

        mf = _BCN_CRONO_FILM_RE.match(ln)
        if not mf or d is None:
            i += 1
            continue

        # El título va pegado a la etiqueta o en la línea siguiente.
        titulo = mf.group(1).strip(" .,:")
        j = i + 1
        if not titulo and j < len(lines):
            titulo = lines[j].strip(" .,:")
            j += 1
        # Ficha técnica: las líneas Dirección/Año/Duración que siguen, hasta la
        # próxima película o el próximo día.
        ficha: dict = {}
        while j < len(lines) and j < i + 10:
            if (_BCN_CRONO_FILM_RE.match(lines[j])
                    or _BCN_CRONO_DIA_RE.match(lines[j])):
                break
            ficha.update(_bcn_parse_ficha(lines[j]))
            j += 1

        if titulo and today <= d:
            titulo, original = _bcn_split_title(titulo)
            out.append(Screening(
                cine="Biblioteca del Congreso",
                title=titulo,
                fecha=d.isoformat(),
                hora=hora,
                ticket_url=ticket_url,
                ciclo=ciclo,
                director=ficha.get("director", ""),
                country=ficha.get("country", ""),
                year=ficha.get("year"),
                duration=ficha.get("duration"),
                original_title=original,
            ))
        i = j
    return out


def _bcn_detail_meta(url: str, soup=None) -> dict:
    """
    Página de detalle de una película: fecha exacta (DD/MM/YYYY), horario,
    link de reserva y ficha técnica.
    """
    out: dict = {}
    if soup is None:
        try:
            soup = fetch_html(url)
        except Exception:
            return out

    body = soup.find("div", class_="row-same-height") or soup
    text = body.get_text("\n", strip=True)

    fechas: list[date] = []
    for dd, mm, yy in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        try:
            fechas.append(date(int(yy), int(mm), int(dd)))
        except ValueError:
            pass
    if fechas:
        out["fechas"] = fechas

    hora = parse_time_str(text)
    if hora:
        out["hora"] = hora

    a = soup.find("a", string=re.compile(r"reserv", re.IGNORECASE))
    if a and a.get("href", "").startswith("http"):
        out["ticket_url"] = a["href"]

    out.update(_bcn_parse_ficha(text))
    return out


def _bcn_card_date(card, day_hint: Optional[int]) -> "tuple[Optional[int], Optional[int]]":
    """Día y mes de la card: del badge (02 / Jul) o del texto ("2 de julio")."""
    badge = card.find("div", class_="agenda-fecha-nueva-content")
    if badge:
        num = badge.find("div", class_="numero")
        mes = badge.find("div", class_="mes")
        if num and mes:
            try:
                day = int(re.sub(r"\D", "", num.get_text(strip=True)))
            except ValueError:
                day = None
            month = MESES_ES.get(mes.get_text(strip=True).strip(". ").lower())
            if day and month:
                return day, month
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)",
                  card.get_text(" ", strip=True), re.IGNORECASE)
    if m:
        month = MESES_ES.get(m.group(2).lower())
        if month:
            return int(m.group(1)), month
    return day_hint, None


def _bcn_resolve_year(day: int, month: int, fechas: list) -> Optional[int]:
    """Año de la función: el de la fecha del detalle que matchea día+mes."""
    for d in fechas:
        if d.day == day and d.month == month:
            return d.year
    today = date.today()
    # Sin detalle: la agenda solo publica funciones futuras → si el mes ya pasó,
    # es del año que viene.
    return today.year + 1 if month < today.month else today.year


def scrape_bcn() -> list[Screening]:
    """
    Scrapea la cartelera del Auditorio Leonardo Favio de la Biblioteca del
    Congreso. Toma cada card de bcn.gob.ar/agenda/cine y la completa con la
    página de detalle (fecha exacta, ficha técnica y link de reserva).
    """
    try:
        soup = fetch_html(BCN_AGENDA)
    except Exception:
        return []

    today = date.today()
    result: list[Screening] = []
    seen: set[tuple] = set()
    # Varias cards de la agenda apuntan a la misma página de ciclo: cacheamos
    # el soup para no bajarla una vez por fecha.
    detalles: dict[str, tuple] = {}
    # Fecha+hora ya resueltas por un cronograma. Las cards de la agenda que
    # caen ahí son las de relleno ("Proyección de X y Z") que el cronograma ya
    # desglosó en películas: se descartan.
    cubiertas: set[tuple] = set()
    pendientes: list[tuple] = []

    for h3 in soup.find_all("h3", class_="titulo_padre"):
        card = h3.find_parent("div", class_="same-height") or h3.find_parent("div")
        if card is None:
            continue

        h2 = card.find("h2", class_="titulo_miniatura")
        if not h2:
            continue
        title, original = _bcn_split_title(h2.get_text(" ", strip=True))
        if not title:
            continue

        ciclo = _BCN_CICLO_RE.sub("", h3.get_text(" ", strip=True)).strip(" .,")

        corta = card.find("div", class_="descripcion_corta")
        meta = _bcn_parse_corta(corta.get_text(" ", strip=True)) if corta else {}

        a = h2.find_parent("a") or card.find("a", href=re.compile(r"bcn\.gob\.ar/"))
        detail_url = a["href"] if a and a.get("href") else BCN_AGENDA
        if detail_url.startswith("/"):
            detail_url = BCN_BASE + detail_url

        if detail_url not in detalles:
            dsoup = None
            if detail_url != BCN_AGENDA:
                try:
                    dsoup = fetch_html(detail_url)
                except Exception:
                    dsoup = None
            detalles[detail_url] = (
                dsoup, _bcn_detail_meta(detail_url, dsoup) if dsoup is not None else {})
        dsoup, detail = detalles[detail_url]

        # Si la página del ciclo trae Cronograma, la card de la agenda no aporta
        # nada: su título es de relleno y su bajada es institucional. Cada
        # película del cronograma es una función propia.
        if dsoup is not None:
            h1 = dsoup.find("h1")
            crono = _bcn_cronograma(
                dsoup,
                (h1.get_text(" ", strip=True) if h1 else "") or ciclo,
                detail.get("ticket_url") or detail_url,
                today,
            )
            if crono:
                for s in crono:
                    k = (s.title, s.fecha, s.hora)
                    if k in seen:
                        continue
                    seen.add(k)
                    result.append(s)
                    cubiertas.add((s.fecha, s.hora))
                continue

        for k in ("director", "country", "year", "duration"):
            if detail.get(k):
                meta[k] = detail[k]

        day, month = _bcn_card_date(card, None)
        if not day or not month:
            continue
        year = _bcn_resolve_year(day, month, detail.get("fechas", []))
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d < today:
            continue

        hora = detail.get("hora") or parse_time_str(card.get_text(" ", strip=True)) or "18:30"

        key = (title, d.isoformat(), hora)
        if key in seen:
            continue
        seen.add(key)
        pendientes.append((d.isoformat(), hora, Screening(
            cine="Biblioteca del Congreso",
            title=title,
            fecha=d.isoformat(),
            hora=hora,
            ticket_url=detail.get("ticket_url") or detail_url,
            ciclo=ciclo,
            director=meta.get("director", ""),
            country=meta.get("country", ""),
            year=meta.get("year"),
            duration=meta.get("duration"),
            original_title=original,
        )))

    # Las cards se emiten al final: recién ahí sabemos qué fechas cubrió algún
    # cronograma (el orden de la agenda no garantiza verlo primero).
    for fecha, hora, s in pendientes:
        if (fecha, hora) not in cubiertas:
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# Archivo General de la Nación  (argentina.gob.ar — Drupal)
# ---------------------------------------------------------------------------
# El AGN no tiene agenda ni ficha por película: hay UNA sola landing que
# reescriben cada mes con el ciclo vigente, y la grilla vive en prosa. Cada
# función es un <p> con esta forma:
#
#     <p><strong>Los Corroboradores</strong><br>
#        Jueves 6 de agosto | 70 min. | Ficción / Documental<br>
#        Dirección: Luis Bernardez</p>
#
# Lo que ese párrafo NO dice —hora y año— está una sola vez al pie, en un
# bloque "Información General" que vale para todo el ciclo. Sin hora no se
# puede publicar una función, así que si ese bloque desaparece preferimos
# devolver [] antes que inventar un horario: la auditoría lo levanta como cine
# caído, que es exactamente lo que pasó.
#
# Ojo con dos cosas de la página:
#   - el bloque de abajo se contradice con los párrafos ("Fecha: 8, 13 y 20 de
#     agosto" cuando las funciones son jueves 6, 13 y 20). Mandan los párrafos:
#     son por película, el otro es un resumen escrito a mano.
#   - los botones "Reservá tu lugar" apuntan todos al MISMO formulario de
#     Microsoft, sin distinguir función, y encima con el href roto
#     ("blank:#https://…", un desliz del editor de Drupal). Como link de la
#     cartelera mandamos la landing del AGN: es lo que le sirve a alguien que
#     quiere ir (tiene ficha, sede y el formulario a un click), y no se pudre
#     cuando el ciclo siguiente cambia de formulario.
# ---------------------------------------------------------------------------

AGN_URL = ("https://www.argentina.gob.ar/interior/archivo-general-de-la-nacion/"
           "cine-en-el-archivo-general-de-la-nacion")

_AGN_FECHA_RE = re.compile(
    r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bados?|domingos?)?\s*"
    r"(\d{1,2}(?:\s*(?:,|y)\s*\d{1,2})*)\s+de\s+(" + "|".join(MESES_ES) + r")\b",
    re.IGNORECASE)
_AGN_HORA_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*h(?:s|oras)?\b", re.IGNORECASE)
_AGN_DUR_RE = re.compile(r"\b(\d{2,3})\s*min", re.IGNORECASE)
_AGN_DIR_RE = re.compile(r"Direcci[oó]n\s*:\s*([^|]+)", re.IGNORECASE)


def _agn_hora(body_text: str) -> Optional[str]:
    """Horario del ciclo, desde "Horario: A las 18 h" (o "18:30 h")."""
    m = re.search(r"Horario\s*:\s*(?:a\s+las\s+)?(\d{1,2})(?::(\d{2}))?\s*h",
                  body_text, re.IGNORECASE)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def _agn_year(body_text: str, month: int) -> int:
    """Año del ciclo. Sale de "Fecha: … de agosto de 2026"; si ese renglón no
    está, se infiere: un mes que ya pasó hace rato es del año que viene (la
    página se publica con un mes de anticipación, no con once de atraso)."""
    m = re.search(r"Fecha\s*:[^\n]*?\bde\s+(20\d{2})", body_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    today = date.today()
    return today.year + 1 if month < today.month - 1 else today.year


def scrape_agn(semanas: int = 9) -> list[Screening]:
    """Scrapea el ciclo de cine del Archivo General de la Nación."""
    try:
        soup = fetch_html(AGN_URL)
    except Exception:
        return []

    body = soup.find("div", class_="field-name-body") or soup
    body_text = body.get_text("\n", strip=True)

    hora = _agn_hora(body_text)
    if not hora:
        return []

    # Ciclo: el primer <h4> del cuerpo es el nombre ("Arquitectura, archivos e
    # historia"); los que siguen son separadores de sección ("Programación de
    # agosto:", "Subte", "Colectivos").
    ciclo = ""
    for h in body.find_all(["h2", "h3", "h4"]):
        t = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
        if t and not re.match(r"^(programaci[oó]n|informaci[oó]n|c[oó]mo llegar)",
                              t, re.IGNORECASE):
            ciclo = t
            break

    today = date.today()
    cutoff = today + timedelta(weeks=semanas)
    result: list[Screening] = []
    seen: set[tuple] = set()

    for p in body.find_all("p"):
        strong = p.find("strong")
        if not strong:
            continue
        crudo = re.sub(r"\s+", " ", strong.get_text(" ", strip=True)).strip()
        # "Fecha: 8, 13 y 20 de agosto de 2026" — el resumen del pie también es
        # negrita + fecha, y sin este corte entra a la cartelera como una
        # película llamada "Fecha". La negrita terminada en ":" es una etiqueta,
        # nunca un título.
        if crudo.endswith(":") or p.find_parent("li"):
            continue
        title = crudo.strip(" .")
        if len(title) < 2:
            continue

        # El resto del párrafo (sin el título) es la línea de datos. Sólo es una
        # función si ahí hay una fecha; así se descartan los otros párrafos en
        # negrita ("Entrada libre y gratuita…", la dirección de la sede).
        resto = p.get_text(" ", strip=True)
        resto = resto.replace(strong.get_text(" ", strip=True), " ", 1)
        m = _AGN_FECHA_RE.search(resto)
        if not m:
            continue

        month = MESES_ES[m.group(2).lower()]
        year = _agn_year(body_text, month)
        # La ficha puede traer su propio horario; si no, manda el del ciclo.
        hm = _AGN_HORA_RE.search(_AGN_DUR_RE.sub(" ", resto))
        hora_f = (f"{int(hm.group(1)):02d}:{int(hm.group(2) or 0):02d}"
                  if hm else hora)

        dm = _AGN_DUR_RE.search(resto)
        duration = int(dm.group(1)) if dm else None
        dirm = _AGN_DIR_RE.search(resto)
        director = re.sub(r"\s+", " ", dirm.group(1)).strip(" .,") if dirm else ""

        for dtxt in re.split(r"\s*(?:,|y)\s*", m.group(1)):
            try:
                d = date(year, month, int(dtxt))
            except ValueError:
                continue
            if d < today or d > cutoff:
                continue
            key = (title, d.isoformat(), hora_f)
            if key in seen:
                continue
            seen.add(key)
            result.append(Screening(
                cine="Archivo General de la Nación",
                title=title,
                fecha=d.isoformat(),
                hora=hora_f,
                ticket_url=AGN_URL,
                ciclo=ciclo,
                director=director,
                duration=duration,
            ))
    return result


# ---------------------------------------------------------------------------
# Funciones manuales — data/manual_screenings.json
# ---------------------------------------------------------------------------
# Escape genérico para lo que ningún scraper puede sacar solo: festivales que
# publican la grilla en prosa (los cortos de Bendita Tú viven dentro de un
# párrafo, no en cards), programas dobles que el sitio escribe como un único
# título, o un cine que rompió justo antes de una función importante.
#
# Ya existían overrides por cine (lorca_manual, museo_manual, cb_manual); éste
# sirve para CUALQUIER sala y además puede DESCARTAR funciones mal scrapeadas,
# que es lo que los otros no saben hacer.
#
# Shape:
#   {"screenings": [ {cine, title, fecha, hora, ...campos de Screening} ],
#    "descartar":  [ {cine, fecha, hora?, title_contiene} ]}
#
# El Letterboxd de estas funciones va en data/metadata_overrides.json, que es
# donde vive ese dato para todo el resto de la cartelera.

MANUAL_PATH = Path(__file__).parent / "data" / "manual_screenings.json"


def _load_manual() -> dict:
    if not MANUAL_PATH.exists():
        return {}
    try:
        return json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[manual] manual_screenings.json ilegible: {e}", flush=True)
        return {}


def scrape_manual(semanas: int = 9) -> list[Screening]:
    """Funciones cargadas a mano, filtradas a [hoy, hoy+semanas]. Las viejas se
    caen solas: no hace falta limpiar el archivo cada mes."""
    data = _load_manual()
    today = date.today()
    end = today + timedelta(weeks=semanas)

    result: list[Screening] = []
    for item in data.get("screenings", []):
        try:
            d = date.fromisoformat(item["fecha"])
        except (KeyError, ValueError):
            continue
        if not (today <= d <= end):
            continue
        result.append(Screening(
            cine=item.get("cine", ""),
            title=item.get("title", ""),
            fecha=item["fecha"],
            hora=item.get("hora", "??"),
            ticket_url=item.get("ticket_url", ""),
            ciclo=item.get("ciclo", ""),
            director=item.get("director", ""),
            country=item.get("country", ""),
            year=item.get("year"),
            duration=item.get("duration"),
            original_title=item.get("original_title", ""),
        ))
    return [s for s in result if s.cine and s.title]


def descartar_manual(screenings: list) -> tuple[list, int]:
    """Saca de la lista las funciones marcadas en `descartar`. Devuelve
    (lista filtrada, cuántas se sacaron).

    Matchea por cine + fecha + substring del título (case-insensitive), con
    hora opcional. Es para funciones que el scraper trae MAL — p.ej. el Museo
    del Cine mete un programa doble en un solo título — y que se reemplazan por
    entradas correctas en `screenings`.
    """
    reglas = _load_manual().get("descartar", [])
    if not reglas:
        return screenings, 0

    def descartada(s) -> bool:
        cine = s.cine if hasattr(s, "cine") else s.get("cine", "")
        fecha = s.fecha if hasattr(s, "fecha") else s.get("fecha", "")
        hora = s.hora if hasattr(s, "hora") else s.get("hora", "")
        title = s.title if hasattr(s, "title") else s.get("title_es", "")
        for r in reglas:
            if r.get("cine") and r["cine"] != cine:
                continue
            if r.get("fecha") and r["fecha"] != fecha:
                continue
            if r.get("hora") and r["hora"] != hora:
                continue
            frag = (r.get("title_contiene") or "").lower()
            if frag and frag not in (title or "").lower():
                continue
            return True
        return False

    filtradas = [s for s in screenings if not descartada(s)]
    return filtradas, len(screenings) - len(filtradas)


# ---------------------------------------------------------------------------
# Cinemark / Hoyts — API propia (bff.cinemark.com.ar)
# ---------------------------------------------------------------------------
# Cinemark y Hoyts son la misma empresa en Argentina (Cinemark Hoyts) y comparten
# backend, así que una sola API cubre las cinco salas del grupo en CABA.
#
# Reemplaza a La Nación para esas salas: trae varios días en vez de sólo hoy,
# más títulos (incluye el cine-evento: recitales, ATEEZ, Katy Perry) y ficha
# propia con director, duración y género. Cinépolis, Showcase y el Lorca no son
# del grupo y siguen por La Nación.
#
# El header `country: AR` es obligatorio — sin él la API responde 500
# "Country undefined not implemented". Y va en MAYÚSCULAS: "ar" también falla.

CINEMARKHOYTS_BFF = "https://bff.cinemark.com.ar/api"
# (theaterId, nombre en la cartelera, ticket_url)
CINEMARKHOYTS_SALAS = [
    (103, "Hoyts Abasto",           "https://www.hoyts.com.ar/"),
    (111, "Hoyts Dot",              "https://www.hoyts.com.ar/"),
    (730, "Cinemark Puerto Madero", "https://www.cinemark.com.ar/"),
    (733, "Cinemark Palermo",       "https://www.cinemark.com.ar/"),
    (734, "Cinemark Caballito",     "https://www.cinemark.com.ar/"),
]
CINEMARKHOYTS_CINES = {nombre for _, nombre, _ in CINEMARKHOYTS_SALAS}


def _cmh_get(path: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"{CINEMARKHOYTS_BFF}/{path}",
            headers={"User-Agent": UA, "Accept": "application/json", "country": "AR"},
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[cmh {path}: {type(e).__name__}]", end=" ", flush=True)
        return None


def _cmh_meta(slug: str, cache: dict) -> dict:
    """Ficha de una película: director, duración, género. Cacheada por slug."""
    if slug in cache:
        return cache[slug]
    out: dict = {}
    d = _cmh_get(f"cinema/movies/slug/{urllib.parse.quote(slug)}")
    m = (d or {}).get("data") or {}
    if m:
        for p in m.get("filmPersons") or []:
            if (p.get("personType") or "").lower() == "director":
                out["director"] = f"{p.get('firstName','')} {p.get('lastName','')}".strip()
                break
        if m.get("runTime"):
            out["duration"] = int(m["runTime"])
    cache[slug] = out
    return out


def scrape_cinemark_hoyts(semanas: int = 2) -> list[Screening]:
    today = date.today()
    end = today + timedelta(weeks=semanas)
    meta_cache: dict = {}
    result: list[Screening] = []

    for theater_id, cine, ticket_url in CINEMARKHOYTS_SALAS:
        sesiones = (_cmh_get(f"cinema/showtimes?theater={theater_id}") or {}).get("data") or []
        if not sesiones:
            print(f"[cmh {cine}: 0 funciones]", end=" ", flush=True)
            continue

        # corporateId → slug, para poder pedir la ficha de cada película.
        slugs = {
            str(m.get("corporateId")): m.get("slug", "")
            for m in ((_cmh_get(f"cinema/movies?theater={theater_id}") or {}).get("data") or [])
        }

        seen: set[tuple] = set()
        for s in sesiones:
            fecha = s.get("sessionDisplayDate") or ""
            # OJO: sessionDateTime termina en "Z" pero la hora ya viene en horario
            # de Buenos Aires (verificado contra la cartelera publicada). Convertir
            # desde UTC correría todas las funciones tres horas.
            hora = (s.get("sessionDateTime") or "")[11:16]
            title = (s.get("movieName") or "").strip()
            if not (fecha and re.fullmatch(r"\d{2}:\d{2}", hora) and title):
                continue
            try:
                d = date.fromisoformat(fecha)
            except ValueError:
                continue
            if not (today <= d <= end):
                continue
            # La misma película a la misma hora en dos salas es una sola función
            # para la cartelera.
            key = (title, fecha, hora)
            if key in seen:
                continue
            seen.add(key)

            meta = _cmh_meta(slugs.get(str(s.get("corporateId")), ""), meta_cache) \
                if slugs.get(str(s.get("corporateId"))) else {}
            result.append(Screening(
                cine=cine,
                title=title,
                fecha=fecha,
                hora=hora,
                ticket_url=ticket_url,
                director=meta.get("director", ""),
                duration=meta.get("duration"),
            ))
    return result


# ---------------------------------------------------------------------------
# Peña sin cadenas — Hasta Trilce (vía alternativateatral.com)
# ---------------------------------------------------------------------------
# Fernando Martín Peña proyecta en fílmico todos los martes en Hasta Trilce.
# La gracia del ciclo es que NO se anuncia qué se da: son dos películas sorpresa
# por noche. Por eso el título, el director y el año son fijos — no hay nada que
# scrapear ahí, y ponerle un título real sería inventarlo.
#
# Las funciones salen del endpoint que usa el propio formulario de compra, que
# devuelve JSON limpio con las que están A LA VENTA:
#     {"funciones": [{"descripcion": "martes 04/08/2026 - 19:00 hs",
#                     "fecha": "04/08/2026", "id": "130899"}, ...]}
# La ficha del espectáculo también publica la grilla ("Martes - 19:00 hs y 21:00
# hs - Del 04/08 al 22/12"), pero de ahí saldrían martes hasta diciembre que
# todavía no existen. El endpoint dice lo que se puede comprar hoy.

PENA_OBRA_ID = "75124"
PENA_API = ("https://publico1.alternativateatral.com/api/formulario-localidades.asp"
            f"?id={PENA_OBRA_ID}&o=14&m=&c=&_=1")
PENA_ENTRADAS = (f"https://publico.alternativateatral.com/"
                 f"entradas{PENA_OBRA_ID}-pena-sin-cadenas?o=14")
PENA_CINE = "Hasta Trilce"
PENA_CICLO = "Peña sin cadenas"
PENA_TITULO = "Película sorpresa"


def scrape_pena_sin_cadenas(semanas: int = 9) -> list[Screening]:
    today = date.today()
    cutoff = today + timedelta(weeks=semanas)
    try:
        crudo = fetch_bytes(PENA_API).decode("utf-8", errors="replace").strip()
    except Exception as e:
        print(f"[peña: no carga — {e}]", end=" ", flush=True)
        return []

    # La respuesta viene envuelta en paréntesis (es un JSONP sin nombre de
    # callback), así que hay que pelarla antes de parsear.
    if crudo.startswith("(") and crudo.endswith(")"):
        crudo = crudo[1:-1]
    try:
        data = json.loads(crudo)
    except Exception:
        print("[peña: respuesta ilegible]", end=" ", flush=True)
        return []

    result: list[Screening] = []
    seen: set = set()
    for f in data.get("funciones") or []:
        md = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (f.get("fecha") or "").strip())
        mh = re.search(r"(\d{1,2}):(\d{2})", f.get("descripcion") or "")
        if not (md and mh):
            continue
        try:
            d = date(int(md.group(3)), int(md.group(2)), int(md.group(1)))
        except ValueError:
            continue
        if not (today <= d <= cutoff):
            continue
        hora = f"{int(mh.group(1)):02d}:{mh.group(2)}"
        if (d, hora) in seen:
            continue
        seen.add((d, hora))
        result.append(Screening(
            cine=PENA_CINE,
            title=PENA_TITULO,
            fecha=d.isoformat(),
            hora=hora,
            ticket_url=PENA_ENTRADAS,
            ciclo=PENA_CICLO,
            director="Desconocido",
            duration=120,
        ))
    if not result:
        print("[peña: 0 funciones a la venta]", end=" ", flush=True)
    return result
