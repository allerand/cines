"""
Scrapers de cartelera para cines de arte de Buenos Aires.
Sala Lugones · Cacodelphia · Cine Lorca · Cine York · MALBA
"""

import re
import urllib.request
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
        out["director"] = md.group(1).strip().rstrip(",")

    # Ciclo: el patrón es "...CICLO_NAME [De DIRECTOR | TITULO_PELICULA]..."
    # Buscamos el ciclo conocido seguido (en algún punto cercano) del título de la
    # página o de "De NAME"
    h1 = soup.find("h1")
    title_text = h1.get_text(strip=True) if h1 else ""
    for ciclo in MALBA_KNOWN_CICLOS:
        # CICLO_NAME (whitespace) FILM_TITLE — la combinación clave
        if title_text and re.search(re.escape(ciclo) + r"\s+" + re.escape(title_text), text):
            out["ciclo"] = ciclo
            break
        # Fallback: CICLO_NAME seguido en pocos chars de "De DIRECTOR"
        if "director" in out:
            if re.search(re.escape(ciclo) + r"[^.]{0,200}\bDe\s+" + re.escape(out["director"]), text):
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

            key = (title, d.isoformat(), hora)
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

async def fetch_ctba_ver_page(page: Page, ver_url: str) -> Optional[str]:
    """Carga la página /ver/ y devuelve el text plano. None si falla."""
    try:
        await page.goto(ver_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
    except Exception:
        return None
    text = await page.evaluate("document.body.innerText")
    return "\n".join(re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines())


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


def parse_ctba_program_text(normalized: str) -> dict[tuple[int, str], dict]:
    """
    Parsea texto plano normalizado de una página /ver/ de ciclo CTBA.
    Devuelve {(day_of_month, "HH:00"): {"title","original_title","country","year","director"}}
    
    Patrón mejorado que captura múltiples películas por día:
      Miércoles 6
      A las 15 y 21 horas
      Juventud en peligro
      (Dangerous Years; EE.UU; 1947)
      Dirección: Arthur Pierson.
      ...
    """
    mapping: dict[tuple[int, str], dict] = {}

    # Split text by day headers; capturing group gives the day-of-month number
    day_re = re.compile(
        r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\s+(\d{1,2})",
        re.IGNORECASE,
    )
    parts = day_re.split(normalized)
    # parts = [preamble, "6", chunk, "7", chunk, ...]

    for i in range(1, len(parts), 2):
        day_num = int(parts[i])
        chunk = parts[i + 1] if i + 1 < len(parts) else ""
        
        # Primero, extraer los horarios del día: "A las 15 y 21 horas" o "A las 15 horas"
        hour_match = re.search(
            r"A las (\d{1,2})(?:\s+y\s+(\d{1,2}))?\s+horas?",
            chunk,
            re.IGNORECASE
        )
        if not hour_match:
            continue
        
        hours = [int(hour_match.group(1))]
        if hour_match.group(2):
            hours.append(int(hour_match.group(2)))
        
        # Ahora extraer cada película del día. Patrón:
        # TITULO
        # (original; país; año)
        # Dirección: director
        film_re = re.compile(
            r"^([A-ZÁÉÍÓÚÑ][^\n(]+?)\s*\n"  # título en su propia línea
            r"\(([^)]+)\)\s*\n?"  # metadata entre paréntesis
            r"(?:Dirección[:\s]+([^\n.]+?))?(?:\n|$)",
            re.MULTILINE | re.IGNORECASE
        )
        
        for fm in film_re.finditer(chunk):
            title = fm.group(1).strip()
            paren_meta = fm.group(2)
            director_raw = fm.group(3)
            
            entry: dict = {"title": title}
            
            # Parse metadata entre paréntesis: "Dangerous Years; EE.UU; 1947"
            pm = re.match(r"\s*([^;]+?)\s*;\s*([^;]+?)\s*;\s*(\d{4})\s*$", paren_meta)
            if pm:
                entry["original_title"] = pm.group(1).strip()
                entry["country"] = pm.group(2).strip()
                entry["year"] = int(pm.group(3))
            
            if director_raw:
                entry["director"] = re.sub(r"\s+", " ", director_raw).strip().rstrip(".")
            
            # Asignar la película a cada hora del día
            for hour in hours:
                mapping[(day_num, f"{hour:02d}:00")] = entry

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
        if ver_url:
            ver_text = await fetch_ctba_ver_page(page, ver_url)
            if ver_text:
                program = parse_ctba_program_text(ver_text)
                # Si no hay programa multi-film, parsear como estreno (peli única)
                if not program:
                    estreno_meta = parse_ctba_estreno_page(ver_text)

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

                    # Look up individual film entry using day + rounded hour
                    entry = (
                        program.get((day, hora))
                        or program.get((day, hora[:2] + ":00"))
                    )
                    if entry:
                        result.append(Screening(
                            cine="Sala Lugones",
                            title=entry["title"],
                            fecha=d.isoformat(), hora=hora,
                            ticket_url=ticket_url,
                            ciclo=cycle_name,
                            director=entry.get("director", ""),
                            country=entry.get("country", ""),
                            year=entry.get("year"),
                        ))
                    elif estreno_meta:
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

async def scrape_cacodelphia(page: Page) -> list[Screening]:
    """
    Página principal → links /pelicula/86/HASH → por cada película, click en
    cada tab de fecha y extraer horarios.
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
                    ))

    return result


# ---------------------------------------------------------------------------
# Cine Lorca  (Wix — la cartelera la suben como imagen, así que se carga
# manualmente desde data/lorca_manual.json)
# ---------------------------------------------------------------------------

import json
from pathlib import Path

LORCA_MANUAL_PATH = Path(__file__).parent / "data" / "lorca_manual.json"


def scrape_lorca() -> list[Screening]:
    """
    Lorca publica su programación como imagen (Wix), así que se mantiene un JSON
    manual con esta forma:
      {
        "period_start": "2026-05-07",   # YYYY-MM-DD
        "period_end":   "2026-05-13",
        "films": [
          {"title": "El drama", "times": ["14:00", "22:10"]},
          ...
        ]
      }
    Genera una Screening por cada (film × hora × día del rango).
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

        # JSON-LD trae startDate/endDate y description con HTML
        description_html = ""
        for sc in ev_soup.find_all("script", type="application/ld+json"):
            try:
                d = _json.loads(sc.string)
            except Exception:
                continue
            if not isinstance(d, dict) or d.get("@type") != "Event":
                continue
            description_html = _html.unescape(d.get("description") or "")
            break
        if not description_html:
            continue

        desc_soup = BeautifulSoup(description_html, "html.parser")
        # Parseamos párrafo por párrafo. Cada <p> tiene este formato típico:
        #   "Sábado 2 de mayo  19 h: TITLE"
        #   "Domingo 17 de mayo  15 h: TITLE_A  17:30 h: TITLE_B"   (multi-slot)
        #   "Sábado 16 de mayo  19 h: El castillo  Nancy"  ← múltiples películas por hora
        # Estrategia: extraer el header de fecha del párrafo, después listar
        # todos los slots "HH(:MM)? h: TITLE" dentro del mismo párrafo.
        date_re = re.compile(
            r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+"
            r"(\d{1,2})\s+de\s+(\w+)(?:\s+(?:de\s+)?(\d{4}))?",
            re.IGNORECASE,
        )
        # Mejorado: captura títulos separados por saltos de línea o espacios dobles
        # Ahora es más permisivo con saltos de línea entre películas
        slot_re = re.compile(
            r"(\d{1,2})(?::(\d{2}))?\s*h(?:s|oras)?\s*[:.\-–]\s*"
            r"(.+?)"
            r"(?=\s+\d{1,2}(?::\d{2})?\s*h(?:s|oras)?\s*[:.\-–]|\Z)",
            re.IGNORECASE | re.DOTALL,  # DOTALL permite que . coincida con saltos de línea
        )

        paragraphs: list[str] = []
        for p in desc_soup.find_all("p"):
            paragraphs.append(re.sub(r"\s+", " ", p.get_text(" ", strip=True)))
        if not paragraphs:
            paragraphs = [re.sub(r"\s+", " ", desc_soup.get_text(" ", strip=True))]

        for para in paragraphs:
            dm = date_re.search(para)
            if not dm:
                continue
            day_num = int(dm.group(1))
            month_name = dm.group(2).lower()
            year = int(dm.group(3)) if dm.group(3) else today.year
            month = CCK_MONTHS.get(month_name)
            if not month:
                continue
            try:
                d = date(year, month, day_num)
            except ValueError:
                continue
            if d < today - timedelta(days=1):
                try:
                    d = date(year + 1, month, day_num)
                except ValueError:
                    continue
            if d < today or d > end:
                continue

            # Slots a partir del fin del header de fecha
            rest = para[dm.end():]
            for sm in slot_re.finditer(rest):
                hour = int(sm.group(1))
                minute = int(sm.group(2)) if sm.group(2) else 0
                raw_title_chunk = sm.group(3).strip(" -–:.,;\n")
                
                # Si hay múltiples títulos separados por salto de línea o dos espacios,
                # procesamos cada uno por separado
                # Split por saltos de línea o múltiples espacios
                titles = re.split(r'\s{2,}|\n', raw_title_chunk)
                
                for raw_title in titles:
                    raw_title = raw_title.strip(" -–:.,;")
                    if not raw_title or len(raw_title) < 2:
                        continue
                    hora = f"{hour:02d}:{minute:02d}"
                    result.append(Screening(
                        cine="CCK",
                        title=raw_title,
                        fecha=d.isoformat(),
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
    end = today + timedelta(weeks=semanas)

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

        # Bloques de horario: "Día1 - Día2 - ... | HH:MM"
        # Puede haber varios: "Ju - Vi | 19:00 Sá - Do | 16:30"
        slot_re = re.compile(
            r"((?:(?:Lu|Ma|Mi|Mié|Mier|Ju|Vi|S[áa]|Do)\b\s*-?\s*)+)\|\s*(\d{1,2}):(\d{2})",
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
            hora = f"{int(m.group(2)):02d}:{m.group(3)}"
            slots.append((weekdays, hora))

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
