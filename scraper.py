"""
Scrapers de cartelera para cines de arte de Buenos Aires.
Sala Lugones · Cacodelphia · Cine Lorca · Cine York · MALBA
"""

import re
import os
import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, timedelta
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
    "sep": 9, "sept": 9, "septiembre": 9,
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

def fetch_html(url: str) -> BeautifulSoup:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return BeautifulSoup(r.read().decode("utf-8", errors="replace"), "html.parser")


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

    # Director: "De NAME" antes de un día de semana (formato MALBA estándar)
    md = re.search(
        r"\bDe\s+([A-ZÁÉÍÓÚÑ][^.\n]{2,60}?)\s+(?:Lunes|Martes|Mi[ée]rcoles|Jueves|"
        r"Viernes|S[áa]bado|Domingo)",
        text,
    )
    if md:
        director = md.group(1).strip().rstrip(",")
        # A veces el texto repite el crédito ("De NOMBRE De NOMBRE") y el regex
        # no-greedy captura ambas ocurrencias. Si es "X De X" dejamos un solo X.
        dup = re.match(r"^(.+?)\s+De\s+\1$", director, re.IGNORECASE)
        if dup:
            director = dup.group(1).strip()
        out["director"] = director

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
    return _MALBA_WD.get(w.translate(_MALBA_ACCENTS).lower()[:3])


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


def _parse_malba_evento(text: str, url: str, today: date, cutoff: date) -> list[Screening]:
    """Parsea una página /evento/ de MALBA: nombre del ciclo + bloque
    'Programación' ("VIERNES 3 22:00 Family portrait, de Lucy Kerr")."""
    ciclo = ""
    mc = re.search(r"Ciclo\s+(.+?)\s+(?:" + _MALBA_WD_RE + r")\s+a\s+las",
                   text, re.IGNORECASE)
    if mc:
        ciclo = mc.group(1).strip()
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
    idx = text.rfind("Programación")
    block = text[idx:] if idx >= 0 else text
    block = re.split(r"\bHacete\b|\bAccede\b|\bSuscrib|\bMalba\b", block)[0]
    out: list[Screening] = []
    seen: set = set()
    for m in _MALBA_EVT_RE.finditer(block):
        d = _malba_resolve_date(_malba_wd(m.group(1)), int(m.group(2)), today, cutoff)
        if not d:
            continue
        hora = f"{int(m.group(3)):02d}:{m.group(4)}"
        title = m.group(5).strip().rstrip(",").strip()
        director = (m.group(6) or "").strip().rstrip(".") or cycle_director
        key = (title, d.isoformat(), hora)
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(Screening(cine="MALBA", title=title, fecha=d.isoformat(),
                             hora=hora, ticket_url=url, ciclo=ciclo, director=director))
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
        out.extend(_parse_malba_evento(esoup.get_text(" ", strip=True), u, today, cutoff))
    return out


def scrape_malba(semanas: int = 2) -> list[Screening]:
    today = date.today()
    end = today + timedelta(weeks=semanas)
    result: list[Screening] = []
    seen: set[tuple] = set()

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

            # Walk up to find a container with both an /evento/ link and a title element
            card = None
            node = span.parent
            for _ in range(15):
                if node is None:
                    break
                link = node.find("a", href=re.compile(r"/evento/"))
                title_el = node.find(class_=re.compile(r"post-title|page-title|entry-title"))
                if link and title_el:
                    card = node
                    break
                node = node.parent

            if card is None:
                continue

            link = card.find("a", href=re.compile(r"/evento/"))
            title_el = card.find(class_=re.compile(r"post-title|page-title|entry-title"))
            ticket_url = link["href"] if link else ""
            title = title_el.get_text(strip=True) if title_el else ""

            if not title:
                continue
            # Skip ciclo cards (ej "Generación del 60") — sus pelis individuales
            # aparecen por separado en otros cards
            if title in MALBA_KNOWN_CICLOS:
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

    # Ciclos vía páginas /evento/ (la agenda día-a-día se los pierde).
    try:
        for s in scrape_malba_eventos(today, end):
            key = (re.sub(r"\s+", " ", s.title).strip().lower(), s.fecha, s.hora)
            if key not in seen:
                seen.add(key)
                result.append(s)
    except Exception:
        pass

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
    hour_re = re.compile(
        r"A las (\d{1,2})(?:[.:](\d{2}))?(?:\s+y\s+(\d{1,2})(?:[.:](\d{2}))?)?\s+horas?",
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
                # DM)." — no son un nombre de programa, sólo metadata residual.
                is_film_year = re.search(r"\([^)]*\d{4}[^)]*\)", ln)
                is_format_note = ln.startswith("(") or re.search(r"\d{2,3}\s*['’′]", ln)
                if not is_film_year and not is_format_note and len(ln) <= 60:
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
            # Extraer mes del encabezado tipo "Del miércoles 6 al miércoles 27 de mayo"
            month_match = re.search(
                r"al\s+\w+\s+\d+\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?",
                ver_text, re.IGNORECASE,
            )
            cycle_month: Optional[int] = None
            cycle_year: int = today.year
            if month_match:
                cycle_month = MESES_ES.get(month_match.group(1).lower())
                if month_match.group(2):
                    cycle_year = int(month_match.group(2))
            # Fallback: buscar cualquier mención de mes
            if not cycle_month:
                for m_name, m_num in MESES_ES.items():
                    if len(m_name) > 3 and m_name in ver_text.lower():
                        cycle_month = m_num
                        break

            if cycle_month:
                for (day_num, hora), entries in program.items():
                    try:
                        d = date(cycle_year, cycle_month, day_num)
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
# Cacodelphia  (cineartecacodelphia.com.ar — Vue SPA)
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


async def scrape_cacodelphia(page: Page) -> list[Screening]:
    """
    Página principal → links /pelicula/86/HASH → por cada película, click en
    cada tab de fecha y extraer horarios. La ficha no trae director/año en
    texto, así que los inferimos del título del trailer de YouTube (oEmbed)
    para que el enrichment valide bien y no matchee la película equivocada.
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
        title = p_el.get_text(strip=True) if p_el else ""
        title = re.sub(r"\s+", " ", title).strip()
        if title and len(title) > 1 and title.lower() not in NON_TITLES:
            movie_links.append((href, title))

    result: list[Screening] = []
    seen_screenings: set[tuple] = set()

    for href, title in movie_links:
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
                        ticket_url="https://cineartecacodelphia.com.ar/",
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

    current_sala = ""
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln:
            i += 1
            continue
        # Una línea que precede a "COMPRAR ENTRADAS" es el nombre de la sala
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt == "COMPRAR ENTRADAS":
            current_sala = ln
            i += 2  # saltamos al primer formato/horario
            continue
        # Una línea con formato: HH:MM[, HH:MM...]
        m = re.match(r"^[^:]+:\s*((?:\d{1,2}:\d{2})(?:\s*,\s*\d{1,2}:\d{2})*)\s*$", ln)
        if m and current_sala:
            for t in re.findall(r"\d{1,2}:\d{2}", m.group(1)):
                hh, mm = t.split(":")
                hora = f"{int(hh):02d}:{mm}"
                out.setdefault(current_sala, []).append(hora)
        i += 1
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
    except Exception:
        return []

    film_paths: list[tuple[str, str]] = []  # (path, title-from-listing)
    seen: set[str] = set()
    for a in sala_soup.find_all("a", href=re.compile(r"^/cartelera-de-cine/pelicula/")):
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True)
        if title and len(title) > 1:
            film_paths.append((href, title))

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
# IMDb sirve la semana completa (multi-día) y La Nación solo el día actual.
# Estrategia: probar IMDb primero. Si devuelve 0 funciones, fallback a
# La Nación para no perder al menos el día de hoy.

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
     "",                                      "",                            "C1428"),
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
        print(f"  · {cine_name}...", end=" ", flush=True)
        ss: list[Screening] = []
        # 1) IMDb
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


def scrape_lorca() -> list[Screening]:
    """
    Fallback manual cuando IMDb falla. Lee data/lorca_manual.json con shape:
      {"period_start": "...", "period_end": "...",
       "films": [{"title": "...", "times": ["HH:MM", ...]}, ...]}
    """
    if not LORCA_MANUAL_PATH.exists():
        return []
    try:
        data = json.loads(LORCA_MANUAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    try:
        start = date.fromisoformat(data["period_start"])
        end = date.fromisoformat(data["period_end"])
    except (KeyError, ValueError):
        return []

    today = date.today()
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


def scrape_cck(semanas: int = 2) -> list[Screening]:
    """
    1. Lista events desde palaciolibertad.gob.ar/cine/
    2. Cada event tiene JSON-LD con "description" en HTML que detalla
       fecha + hora + título de cada función dentro del ciclo.
    
    Manejo especial para eventos con múltiples películas por horario:
    Ejemplo: "19 h: El castillo  Nancy"
    Se parsea como DOS películas separadas.
    """
    BASE = "https://palaciolibertad.gob.ar"
    try:
        soup = fetch_html(f"{BASE}/cine/")
    except Exception:
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
        try:
            ev_soup = fetch_html(event_url)
        except Exception:
            continue
        h1 = ev_soup.find("h1")
        cycle_name = h1.get_text(strip=True) if h1 else ""

        # JSON-LD trae startDate/endDate y description con HTML.
        description_html = ""
        start_iso = end_iso = ""
        for sc in ev_soup.find_all("script", type="application/ld+json"):
            try:
                d = _json.loads(sc.string)
            except Exception:
                continue
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
        slot_re = re.compile(
            r"(\d{1,2})(?::(\d{2}))?\s*h(?:s|oras)?\s*[:.\-–]\s*"
            r"(.+?)"
            r"(?=\s+\d{1,2}(?::\d{2})?\s*h(?:s|oras)?\s*[:.\-–]|\Z)",
            re.IGNORECASE | re.DOTALL,
        )

        # Procesamos la descripción entera y agrupamos por header de fecha.
        # Si nunca aparece un header de fecha, los slots se asignan a ev_start.
        full_text = desc_soup.get_text(" ", strip=True)
        full_text = re.sub(r"\s+", " ", full_text)

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
                titles = re.split(r"\s{2,}|\n", raw_title_chunk)
                for raw_title in titles:
                    raw_title = raw_title.strip(" -–:.,;")
                    if not raw_title or len(raw_title) < 2:
                        continue
                    hora = f"{hour:02d}:{minute:02d}"
                    result.append(Screening(
                        cine="CCK",
                        title=raw_title,
                        fecha=sec_date.isoformat(),
                        hora=hora,
                        ticket_url=event_url,
                        ciclo=cycle_name,
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
# Cine Cosmos UBA  (cinecosmos.uba.ar — sitio estático con detalle por peli)
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


def scrape_cosmos(semanas: int = 2) -> list[Screening]:
    """
    Scrapea cinecosmos.uba.ar. La home lista las pelis con links
    `?c=main&a=Detalle&idPelicula=NNN`. Cada detalle tiene:
        "Dirección: NAME  Año: YYYY  País: PAIS  Duración: NNm
         Ju - Vi - Sá - Do - Lu - Ma - Mi | HH:MM"
    Generamos una Screening por cada (día válido en el rango, hora).
    """
    BASE = "https://www.cinecosmos.uba.ar/"
    try:
        home = fetch_html(BASE)
    except Exception:
        return []

    # IDs únicos de películas en la home
    ids: list[str] = []
    seen_ids: set[str] = set()
    for a in home.find_all("a", href=re.compile(r"idPelicula=\d+")):
        m = re.search(r"idPelicula=(\d+)", a["href"])
        if m and m.group(1) not in seen_ids:
            seen_ids.add(m.group(1))
            ids.append(m.group(1))

    result: list[Screening] = []
    today = date.today()
    # La cartelera de Cosmos va Jueves → Miércoles y se actualiza cada Jueves.
    # No tiene sentido expandir más allá del próximo Miércoles porque después
    # el sitio publica una programación nueva. weekday(): Mon=0 ... Wed=2 ... Sun=6
    days_to_wed = (2 - today.weekday()) % 7
    end = today + timedelta(days=days_to_wed)

    for film_id in ids:
        try:
            soup = fetch_html(f"{BASE}?c=main&a=Detalle&idPelicula={film_id}")
        except Exception:
            continue
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

        # Title — primer h1/h2 o link al detalle dentro de la propia página
        title = ""
        for tag in ("h1", "h2", "h3"):
            el = soup.find(tag)
            if el:
                t = el.get_text(strip=True)
                if t and t.lower() != "cine cosmos":
                    title = t
                    break
        if not title:
            continue

        director = ""
        m = re.search(r"Direcci[óo]n\s*:\s*([^\n]+?)\s+A[ñn]o\s*:", text)
        if m:
            director = m.group(1).strip()

        year: Optional[int] = None
        m = re.search(r"A[ñn]o\s*:\s*(\d{4})", text)
        if m:
            year = int(m.group(1))

        country = ""
        m = re.search(r"Pa[íi]s\s*:\s*([^\n]+?)\s+Duraci[óo]n\s*:", text)
        if m:
            country = m.group(1).strip()

        duration: Optional[int] = None
        m = re.search(r"Duraci[óo]n\s*:\s*(\d{1,3})\s*m\b", text)
        if m:
            duration = int(m.group(1))

        # Bloques de horario: "Día1 - Día2 - ... | HH:MM[ - HH:MM ...]"
        # Cada bloque puede tener VARIOS horarios separados por " - "
        # (p.ej. "Ju Vi Sá Do Lu Ma Mi | 18:40 - 21:00") y puede haber varios
        # bloques ("Ju - Vi | 19:00 Sá - Do | 16:30"). El grupo de horarios
        # captura sólo dígitos/":"/espacios/guiones, así que se corta solo al
        # llegar al próximo bloque de días (letras).
        slot_re = re.compile(
            r"((?:(?:Lu|Ma|Mi|Mié|Mier|Ju|Vi|S[áa]|Do)\b\s*-?\s*)+)\|\s*([\d:\s\-–—,]+)",
            re.IGNORECASE,
        )
        slots: list[tuple[set[int], str]] = []
        for m in slot_re.finditer(text):
            days_chunk = m.group(1).lower()
            weekdays: set[int] = set()
            for tok in re.findall(r"[a-záéí]+", days_chunk):
                if tok in COSMOS_DAY_ABBREV:
                    weekdays.add(COSMOS_DAY_ABBREV[tok])
            if not weekdays:
                continue
            for hh, mm in re.findall(r"(\d{1,2}):(\d{2})", m.group(2)):
                slots.append((weekdays, f"{int(hh):02d}:{mm}"))

        if not slots:
            continue

        # Expandir a fechas concretas
        d = today
        while d <= end:
            for weekdays, hora in slots:
                if d.weekday() in weekdays:
                    result.append(Screening(
                        cine="Cine Cosmos",
                        title=title,
                        fecha=d.isoformat(),
                        hora=hora,
                        ticket_url=f"{BASE}?c=main&a=Detalle&idPelicula={film_id}",
                        director=director,
                        country=country,
                        year=year,
                        duration=duration,
                    ))
            d += timedelta(days=1)

    return result


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
    rf"(\d{{1,2}})(?::(\d{{2}}))?\s*(?:h|hs|horas?)\b",
    re.IGNORECASE,
)


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


async def scrape_arthaus(page: Page, semanas: int = 3) -> list[Screening]:
    """Scrapea la agenda de arthaus.ar.

    La web pasó a una agenda única (/agenda/) que mezcla todos los tipos de
    evento (cine, música, etc.). Cada evento es una tarjeta con un botón
    "VER DETALLE". Tomamos las tarjetas de cine y entramos a la página de cada
    película para sacarle la data (fechas, hora, director, año).
    """
    today = date.today()
    # Arthaus programa cada película en ~2 funciones repartidas en 2-3 semanas
    # (p.ej. Olivia: vie 12 y dom 21). Con la ventana global corta (2 semanas)
    # se perdían las segundas fechas, así que la ampliamos para esta sala.
    cutoff = today + timedelta(weeks=max(semanas, 5))

    # Usamos domcontentloaded (no networkidle): la agenda tiene analytics/widgets
    # que mantienen conexiones abiertas y hacen que networkidle se cuelgue hasta
    # el timeout. Compensamos con una espera fija + scroll para el lazy-load.
    await page.goto(ARTHAUS_AGENDA_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    for _ in range(10):
        await page.mouse.wheel(0, 1600)
        await page.wait_for_timeout(500)

    # Juntamos, por tarjeta, el link "VER DETALLE" y el texto de la tarjeta
    # (para descartar lo que no sea cine sin tener que abrir cada detalle).
    cards = await page.evaluate(
        """() => {
            const out = [];
            const seen = new Set();
            for (const a of Array.from(document.querySelectorAll('a[href]'))) {
                const label = (a.textContent || '').trim().toLowerCase().replace(/\\s+/g, ' ');
                const isDetalle = label === 'ver detalle';
                const href = a.href;
                if (!href || seen.has(href)) continue;
                // Link de detalle directo, o (fallback) link a un permalink de agenda.
                const looksLikeEvent = /\\/agenda\\/[^/]+\\/?$/.test(new URL(href).pathname);
                if (!isDetalle && !looksLikeEvent) continue;
                let card = a;
                for (let k = 0; k < 6 && card.parentElement; k++) {
                    card = card.parentElement;
                    if ((card.textContent || '').length > 140) break;
                }
                seen.add(href);
                out.push({ href, text: (card.textContent || '').replace(/\\s+/g, ' ').trim() });
            }
            return out;
        }"""
    )

    # Pre-filtro por "cine" en el texto de la tarjeta (la categoría/el prefijo
    # "CINE ARTHAUS." aparecen ahí). La categoría se re-verifica en el detalle.
    detail_urls: list[str] = []
    for c in cards:
        if "cine" in (c.get("text", "")).lower():
            detail_urls.append(c["href"])
    # Salvaguarda: si el pre-filtro no encontró nada (p.ej. el texto visible de
    # la tarjeta no incluía "cine"), visitamos todas — el parser de detalle
    # descarta lo que no sea cine vía la CATEGORÍA.
    if not detail_urls:
        detail_urls = [c["href"] for c in cards]
    # Dedup preservando orden y tope defensivo para acotar la duración total.
    seen_urls: set[str] = set()
    detail_urls = [u for u in detail_urls if not (u in seen_urls or seen_urls.add(u))]
    detail_urls = detail_urls[:80]

    print(f"  Arthaus: {len(cards)} tarjetas, {len(detail_urls)} candidatas de cine")

    result: list[Screening] = []
    for url in detail_urls:
        try:
            # domcontentloaded + espera corta: las páginas de detalle son WP
            # renderizadas en servidor, no necesitan esperar a networkidle.
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(500)
            title_raw = await page.evaluate(
                "() => { const h = document.querySelector('h1'); return h ? h.innerText : document.title; }"
            )
            body = await page.evaluate("document.body.innerText")
        except Exception as e:
            print(f"  Arthaus: error en {url}: {e}")
            continue
        result.extend(_parse_arthaus_detail(title_raw, body, url, today, cutoff))

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


async def scrape_cc25(page: Page, semanas: int = 3) -> list[Screening]:
    """Scrapea cc25.org/cine: junta los links 'Ver detalle' (/eventos/) y entra a
    cada uno a sacar fecha/hora/título/director (filtrando CATEGORÍA = Cine)."""
    today = date.today()
    cutoff = today + timedelta(weeks=max(semanas, 6))
    try:
        await page.goto(CC25_CINE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        for _ in range(8):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(450)
        links = await page.eval_on_selector_all(
            'a[href*="/eventos/"]', "els => els.map(e => e.href)")
    except Exception:
        return []
    links = [u for u in dict.fromkeys(links or []) if "/eventos/" in u][:40]

    result: list[Screening] = []
    for url in links:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(600)
            h1 = await page.evaluate(
                "() => { const h = document.querySelector('h1'); return h ? h.innerText : ''; }")
            body = await page.evaluate("document.body.innerText")
        except Exception:
            continue
        result.extend(_parse_cc25_detail(h1, body, url, today, cutoff))
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

def _borges_http_json(url: str, browser_headers: bool = True):
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
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _borges_proxy_url(target: str) -> Optional[str]:
    """Envuelve la URL objetivo en un servicio de scraping con IPs residenciales
    para saltear el bloqueo de Cloudflare a la IP del runner. Requiere el secret
    BORGES_SCRAPER_KEY. Por defecto usa el formato de ScraperAPI (ultra_premium =
    residencial + anti-Cloudflare); se puede cambiar de proveedor con
    BORGES_SCRAPER_URL_TEMPLATE, p.ej. scrape.do:
        https://api.scrape.do/?token={key}&super=true&url={url}
    """
    key = os.environ.get("BORGES_SCRAPER_KEY")
    if not key:
        return None
    tmpl = (os.environ.get("BORGES_SCRAPER_URL_TEMPLATE")
            or "https://api.scraperapi.com/?api_key={key}&ultra_premium=true&url={url}")
    return tmpl.format(key=urllib.parse.quote(key, safe=""),
                       url=urllib.parse.quote(target, safe=""))


def fetch_borges_json(url: str) -> Optional[dict | list]:
    """Trae un JSON de la API del Borges. Primero prueba directo (headers de
    navegador). Si Cloudflare bloquea la IP del runner, reintenta a través de un
    servicio de scraping con IPs residenciales — sólo si está configurado el
    secret BORGES_SCRAPER_KEY. Si todo falla, devuelve None (Borges queda vacío
    sin romper el resto del scrapeo)."""
    try:
        return _borges_http_json(url, browser_headers=True)
    except Exception as direct_err:
        proxy = _borges_proxy_url(url)
        if not proxy:
            print(f"  · [Borges API Error] {direct_err} "
                  "(configurá BORGES_SCRAPER_KEY para usar un servicio de scraping)")
            return None
        try:
            return _borges_http_json(proxy, browser_headers=False)
        except Exception as proxy_err:
            print(f"  · [Borges API Error] directo: {direct_err}; servicio: {proxy_err}")
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
    events_list = fetch_borges_json(BORGES_API_LIST)
    if not events_list or not isinstance(events_list, list):
        print("  · [Borges API] Lista de eventos vacía o inaccesible.")
        return []

    result: list[Screening] = []
    seen: set = set()
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
        detail = (fetch_borges_json(f"{BORGES_API_DETAIL}{ev_id}") or {}) if needs_detail else {}
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

    print(f"  · [Borges API] Procesadas con éxito {len(result)} funciones.")
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
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = _json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
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

    # Horario del ciclo (arriba: "19:00 hs · Colón 1133 · Avellaneda").
    default_hora = "19:00"
    hm = re.search(r"(\d{1,2}):(\d{2})\s*hs", text)
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

        # Título / director / año / ciclo dentro de la card (hasta el próximo
        # "Director · Año", que cierra el bloque de metadata).
        title = ciclo = director = ""
        film_year: Optional[int] = None
        k = j + 1
        while k < n and k < j + 10:
            row = lines[k]
            if not row:
                k += 1
                continue
            cm = re.match(r"ciclo\s*·\s*(.+)$", row, re.IGNORECASE)
            if cm:
                ciclo = cm.group(1).strip()
                k += 1
                continue
            dm = _CEA_DIR_YEAR_RE.match(row)
            if dm:
                director, film_year = dm.group(1).strip(), int(dm.group(2))
                break
            if re.fullmatch(r"\d{1,2}", row):
                break
            if not title:
                title = row
            k += 1

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
        await page.wait_for_timeout(2500)
        # Sólo necesitamos las cards de arriba (las reservables) + los links a
        # los formularios de reserva; un scroll moderado alcanza.
        for _ in range(8):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(400)
        text = await page.evaluate("document.body.innerText")
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
_CB_DOW = r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo"
_CB_FUNC_RE = re.compile(
    r"^(?:" + _CB_DOW + r")\s+(\d{1,2})"
    r"(?:\s+de\s+(" + "|".join(_CB_MESES) + r"))?"
    r"[.,]?\s*(?:(\d{1,2})(?::(\d{2}))?\s*HS\b)?",
    re.IGNORECASE)
_CB_RANGE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_CB_MESES) + r")\s+(\d{4})", re.IGNORECASE)


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
    for d, m, y in _CB_RANGE_RE.findall(txt):
        try:
            ds.append(date(int(y), _CB_MESES[m.lower()], int(d)))
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


def _cb_parse_film(rest: str) -> "tuple[str, Optional[int], str, Optional[int]]":
    """De la cola de una línea de función saca (título, año, director, duración)."""
    rest = re.sub(r"^(PRE\s*ESTRENO|ESTRENO|FUNCI[ÓO]N\s+ESPECIAL)[\s:.\-]*",
                  "", rest, flags=re.IGNORECASE).strip()
    ym = re.search(r"\((\d{4})\)", rest)
    year = int(ym.group(1)) if ym else None
    title = (rest[:ym.start()] if ym
             else re.split(r"\bDir\b|Direcci|Guion|Dur\.", rest)[0]).strip(" .,–-")
    director = ""
    dm = re.search(r"(?:Guion y direcci[oó]n|Direcci[oó]n|Dir)\.?\s*:?\s*([^.\n]+)",
                   rest, re.IGNORECASE)
    if dm:
        cand = re.split(r"\b\d+\s*min", dm.group(1))[0].strip(" .,")
        # Sin delimitador claro la sinopsis se pega al nombre: si es largo, lo
        # dejamos vacío y que Letterboxd complete el director.
        if len(cand) <= 40 and len(cand.split()) <= 5:
            director = cand
    durm = re.search(r"(\d{1,3})\s*(?:min|minutos)\b", rest, re.IGNORECASE)
    duration = int(durm.group(1)) if durm else None
    return title, year, director, duration


def _cb_parse_detail(soup, url: str) -> list[Screening]:
    h1 = soup.find(["h1", "h2"])
    title_full = h1.get_text(" ", strip=True) if h1 else ""
    ciclo = title_full.split("|", 1)[1].strip() if "|" in title_full else title_full
    start, end = _cb_cuando(soup)
    hora_default = _cb_horario(soup)
    art = soup.find("div", class_="article") or soup

    out: list[Screening] = []
    seen: set[tuple] = set()
    for p in art.find_all(["p", "li"]):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        m = _CB_FUNC_RE.match(t)
        if not m:
            continue
        day = int(m.group(1))
        month = _CB_MESES[m.group(2).lower()] if m.group(2) else (
            start.month if start else None)
        if not month:
            continue
        hora = (f"{int(m.group(3)):02d}:{int(m.group(4) or 0):02d}"
                if m.group(3) else hora_default)
        title, year, director, duration = _cb_parse_film(t[m.end():].strip())
        if not title or len(title) < 2:
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
        except Exception:
            break
        cards = soup.select("div.agenda div.card")
        if not cards:
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


def scrape_cb(max_pages: int = 3) -> list[Screening]:
    """
    Scrapea la cartelera de cine de la Casa Nacional del Bicentenario.
    Descubre las actividades de cine y parsea cada ciclo en funciones
    individuales (una película por fecha).
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
    return result
