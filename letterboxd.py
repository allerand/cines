"""
Enriquecimiento con datos de Letterboxd:
  - URL exacta de la película
  - Título en inglés
  - Director
  - País de origen
  - Año

Estrategia:
  1. Construir slug desde el título → probar URL directa
  2. Si falla → buscar con playwright en letterboxd.com/search/
  3. Parsear la página de la película para obtener metadatos
"""

import asyncio
import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

# Sin hints (año/director) para desambiguar, rechazamos películas más viejas que
# este corte: casi siempre son homónimos equivocados en salas que programan
# estrenos (Cacodelphia, Lorca). Ej.: "Familia" (Costabile, 2024) matcheaba con
# una "Familia" de 1992.
_NO_HINT_MIN_YEAR = date.today().year - 8

from bs4 import BeautifulSoup

# Playwright sólo se necesita para enrich_title (búsqueda en LB con headless
# browser). Lo importamos perezosamente para que las funciones TMDb / utilities
# puedan usarse sin tener playwright instalado.
if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Page

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Ciclos y programas que NO son películas individuales
NON_FILMS = {
    "generación del 60", "generacion del 60",
    "revista caligari", "cineclub nocturna",
    "canapé session", "canape session",
    "ciclo", "session", "película sorpresa",
    "cielos rojos", "claude chabrol bis", "érase una vez con",
}


def is_non_film(title: str) -> bool:
    t = title.lower()
    return any(nf in t for nf in NON_FILMS)


def slugify(text: str) -> str:
    """'El Príncipe de Nanawa' → 'el-principe-de-nanawa'"""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def fetch_film_page(url: str) -> Optional[BeautifulSoup]:
    """Intenta cargar una página de Letterboxd con requests. None si falla."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status == 200:
                return BeautifulSoup(r.read().decode("utf-8", errors="replace"), "html.parser")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        pass
    return None


def parse_film_soup(soup: BeautifulSoup, url: str) -> Optional[dict]:
    """
    Extrae metadatos de la página de una película de Letterboxd.
    Selectores verificados:
      title:    h1.headline-1 > span.name  (h1.site-logo is the branding)
      director: a[href*="/director/"]
      year:     a[href*="/films/year/"]
      country:  a[href*="/films/country/"]
    """
    # h1.site-logo contains "Letterboxd — Your life in film" — skip it
    title_h1 = soup.find("h1", class_="headline-1")
    if title_h1:
        span = title_h1.find("span", class_="name")
        title_en = span.get_text(strip=True) if span else title_h1.get_text(strip=True)
    else:
        # Fallback: parse <title> tag "Film Name (Year) — Letterboxd"
        title_tag = soup.find("title")
        if not title_tag:
            return None
        title_en = re.sub(r"\s*\(\d{4}\).*$", "", title_tag.get_text(strip=True)).strip()
        if not title_en:
            return None

    director_links = soup.find_all("a", href=re.compile(r"/director/"))
    seen_dirs: list[str] = []
    for a in director_links:
        name = a.get_text(strip=True)
        if name and name not in seen_dirs:
            seen_dirs.append(name)
    director = ", ".join(seen_dirs[:3])

    year_link = soup.find("a", href=re.compile(r"/films/year/\d+"))
    year: Optional[int] = None
    if year_link:
        m = re.search(r"/films/year/(\d{4})", year_link["href"])
        if m:
            year = int(m.group(1))

    country_links = soup.find_all("a", href=re.compile(r"/films/country/"))
    countries = [a.get_text(strip=True) for a in country_links if a.get_text(strip=True)]
    country = ", ".join(countries[:2]) if countries else ""

    # Duration in minutes — Letterboxd shows "97 mins" in p.text-link.text-footer
    duration: Optional[int] = None
    footer = soup.find("p", class_=re.compile(r"text-footer"))
    if footer:
        dm = re.search(r"(\d+)\s*mins?\b", footer.get_text(" ", strip=True))
        if dm:
            duration = int(dm.group(1))

    # Géneros: links /films/genre/SLUG/. LB usa slugs en inglés, traducimos.
    LB_GENRE_ES = {
        "action": "Acción", "adventure": "Aventura", "animation": "Animación",
        "comedy": "Comedia", "crime": "Crimen", "documentary": "Documental",
        "drama": "Drama", "family": "Familiar", "fantasy": "Fantasía",
        "history": "Historia", "horror": "Terror", "music": "Música",
        "mystery": "Misterio", "romance": "Romance",
        "science-fiction": "Ciencia ficción", "tv-movie": "TV",
        "thriller": "Thriller", "war": "Bélica", "western": "Western",
    }
    genre_slugs: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"^/films/genre/[^/]+/?$")):
        m = re.match(r"^/films/genre/([^/]+)/?$", a["href"])
        if m and m.group(1) not in genre_slugs:
            genre_slugs.append(m.group(1))
    genres = [LB_GENRE_ES.get(s, s.replace("-", " ").capitalize()) for s in genre_slugs[:2]]
    genre = ", ".join(genres)

    return {
        "url": url,
        "title_en": title_en,
        "director": director,
        "country": country,
        "year": year,
        "duration": duration,
        "genre": genre,
    }


async def search_letterboxd(page: "Page", query: str) -> Optional[str]:
    """
    Busca en letterboxd.com/search/ con playwright y devuelve la URL de la primera película.
    (urllib devuelve 403 en el search endpoint de Letterboxd)
    """
    from urllib.parse import quote_plus
    search_url = f"https://letterboxd.com/search/{quote_plus(query)}/"
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
    except Exception:
        return None

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=re.compile(r"^/film/")):
        href = a["href"]
        if re.match(r"^/film/[^/]+/?$", href):
            return "https://letterboxd.com" + href.rstrip("/") + "/"

    return None


class LetterboxdCache:
    """Cache persistente en JSON para evitar re-consultas."""

    def __init__(self, cache_path: Path):
        self.path = cache_path
        self._data: dict = {}
        if cache_path.exists():
            try:
                self._data = json.loads(cache_path.read_text())
            except Exception:
                self._data = {}

    def get(self, key: str) -> Optional[dict]:
        return self._data.get(key.lower())

    def set(self, key: str, meta: dict) -> None:
        self._data[key.lower()] = meta
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))

    def has(self, key: str) -> bool:
        return key.lower() in self._data


_STOPWORDS_NAME = {"de", "del", "la", "el", "los", "las", "y", "and", "the"}


def _name_overlap(a: str, b: str) -> bool:
    """True si dos nombres comparten al menos una palabra significativa (>3 chars)."""
    if not a or not b:
        return False
    def words(s: str) -> set[str]:
        norm = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode("ascii")
        return {w for w in re.split(r"[\s,;.\-]+", norm) if len(w) > 3 and w not in _STOPWORDS_NAME}
    return bool(words(a) & words(b))


def _validate_meta(
    meta: dict,
    hint_year: Optional[int],
    hint_director: str,
    hint_duration: Optional[int] = None,
) -> bool:
    """
    Decide si el match de Letterboxd es coherente con la metadata del cine.
      - Si hint_year ±2 difiere del LB year → rechazar
      - Si hint_director y LB director no comparten ninguna palabra → rechazar
      - Si meta no trae director ni year, no podemos validar → rechazar también
        cuando hay hint_director (mejor empty que wrong)
      - Si hint_duration ±5 difiere del LB duration → rechazar
      - Sin NINGÚN hint, rechazar pelis más viejas que _NO_HINT_MIN_YEAR
        (homónimos equivocados en salas de estrenos).
    """
    if hint_year and meta.get("year"):
        if abs(int(meta["year"]) - int(hint_year)) > 2:
            return False
    if hint_director:
        lb_director = meta.get("director") or ""
        if not lb_director:
            return False  # sin LB director y con hint, no podemos confirmar → rechazar
        if not _name_overlap(hint_director, lb_director):
            return False
    if hint_duration and meta.get("duration"):
        if abs(int(meta["duration"]) - int(hint_duration)) > 5:
            return False
    # Sin ningún hint para desambiguar, una peli claramente vieja es casi siempre
    # un homónimo equivocado (salas de estrenos). Mejor empty que wrong.
    if not hint_year and not hint_director and meta.get("year"):
        if int(meta["year"]) < _NO_HINT_MIN_YEAR:
            return False
    return True


_SPANISH_STOPWORDS = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "a"}


def _normalize_for_imdb(query: str) -> str:
    """
    IMDB suggestion API funciona mejor sin acentos y sin stopwords ES.
    Ej: "La hija de Drácula" → "hija dracula" → matchea Dracula's Daughter (1936).
    """
    s = unicodedata.normalize("NFKD", query)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _SPANISH_STOPWORDS]
    return " ".join(words)


def imdb_suggest(query: str) -> list[dict]:
    """
    Llama al endpoint público de autocomplete de IMDB y devuelve hasta 5
    candidatos: [{'tt', 'title', 'year'}, ...]. No requiere auth ni JS.
    Normaliza la query removiendo stopwords ES y acentos.
    """
    import urllib.parse, json
    normalized = _normalize_for_imdb(query)
    q = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not q:
        return []
    first = q[0]
    url = f"https://v3.sg.media-imdb.com/suggestion/{first}/{urllib.parse.quote(q)}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception:
        return []
    out: list[dict] = []
    for d in data.get("d", [])[:5]:
        tt = d.get("id", "")
        if tt.startswith("tt"):
            out.append({
                "tt": tt,
                "title": d.get("l", ""),
                "year": d.get("y"),
            })
    return out


# ---------------------------------------------------------------------------
# TMDb fallback — acepta TMDB_API_KEY (key v3, ~32 chars hex) o
# TMDB_READ_ACCESS_TOKEN (token v4, JWT con puntos). El código detecta el tipo:
# - v3 → se manda como ?api_key=...
# - v4 → se manda como Authorization: Bearer ...
# Si ninguna env var está seteada, las funciones devuelven {} y no bloquean.
# ---------------------------------------------------------------------------

import os as _os


def _tmdb_credential() -> tuple[str, str]:
    """Devuelve (kind, value) donde kind ∈ {'v3','v4',''}."""
    v4 = _os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
    if v4:
        return ("v4", v4)
    v3 = _os.environ.get("TMDB_API_KEY", "").strip()
    if v3:
        # Heurística: tokens v4 son JWTs (contienen puntos). Si por error
        # alguien pegó un v4 en TMDB_API_KEY, lo usamos como Bearer.
        if v3.count(".") >= 2 and len(v3) > 100:
            return ("v4", v3)
        return ("v3", v3)
    return ("", "")


def _tmdb_request(path: str, params: dict) -> dict:
    """Hace un GET a la API TMDb v3 manejando ambas credenciales."""
    import urllib.parse
    kind, cred = _tmdb_credential()
    if not kind:
        return {}
    if kind == "v3":
        params = {**params, "api_key": cred}
    url = "https://api.themoviedb.org/3" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if kind == "v4":
        headers["Authorization"] = f"Bearer {cred}"
    try:
        req = urllib.request.Request(url, headers=headers)
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception:
        return {}


def tmdb_search_movie(title: str, year: Optional[int] = None) -> list[dict]:
    """Busca en TMDb y devuelve hasta 5 candidatos: [{id, title, original_title, year}, ...]."""
    params = {"query": title, "include_adult": "false"}
    if year:
        params["year"] = str(year)
    data = _tmdb_request("/search/movie", params)
    out: list[dict] = []
    for r in data.get("results", [])[:5]:
        out.append({
            "id": r.get("id"),
            "title": r.get("title") or "",
            "original_title": r.get("original_title") or "",
            "year": int(r["release_date"][:4]) if r.get("release_date") else None,
        })
    return out


def tmdb_imdb_id(movie_id: int) -> Optional[str]:
    """IMDb id (ttXXXXXX) de una película de TMDb, o None."""
    data = _tmdb_request(f"/movie/{movie_id}/external_ids", {})
    tt = data.get("imdb_id") or ""
    return tt if tt.startswith("tt") else None


def tmdb_letterboxd_candidates(
    title: str,
    hint_original: str,
    hint_year: Optional[int],
    min_year_no_hint: Optional[int] = None,
) -> list[str]:
    """
    Descubre URLs de Letterboxd vía TMDb search → IMDb id → /imdb/tt redirect.

    TMDb matchea títulos traducidos y AKAs mucho mejor que el slug guessing
    y que la suggestion API de IMDb (ej: "Obsesión" (2025) → Obsession de
    Curry Barker, cuyo slug es inglés y "obsesion" no es prefijo de
    "obsession"). Sin credencial de TMDb devuelve [].
    """
    if not _tmdb_credential()[0]:
        return []
    queries: list[tuple[str, Optional[int]]] = []
    if hint_original:
        queries.append((hint_original, hint_year))
    queries.append((title, hint_year))
    urls: list[str] = []
    seen_ids: set[int] = set()
    for q, y in queries:
        for cand in tmdb_search_movie(q, y):
            mid = cand.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            cy = cand.get("year")
            if hint_year and cy and abs(int(cy) - int(hint_year)) > 2:
                continue
            if not hint_year and cy and min_year_no_hint and int(cy) < min_year_no_hint:
                continue
            tt = tmdb_imdb_id(mid)
            if not tt:
                continue
            lb_url = letterboxd_url_from_imdb(tt)
            if lb_url and lb_url not in urls:
                urls.append(lb_url)
            if len(urls) >= 3:
                return urls
    return urls


def fetch_tmdb_movie_meta(movie_id: int) -> dict:
    """Trae detalles + credits de TMDb. Devuelve {director, country, duration,
    year, title_en, title_es, original_title}.

    title_es: traducción oficial al español si existe (vía endpoint
    /translations). Si TMDb no tiene una traducción al español, queda vacío
    para que el caller use el título original.
    """
    data = _tmdb_request(f"/movie/{movie_id}", {"append_to_response": "credits,translations", "language": "en-US"})
    if not data:
        return {}
    out: dict = {}
    if data.get("title"):
        out["title_en"] = data["title"]
    if data.get("original_title"):
        out["original_title"] = data["original_title"]
    if data.get("runtime"):
        out["duration"] = int(data["runtime"])
    if data.get("release_date"):
        out["year"] = int(data["release_date"][:4])
    countries = [c.get("name") for c in data.get("production_countries", []) if c.get("name")]
    if countries:
        out["country"] = ", ".join(countries[:2])
    directors = [
        c.get("name") for c in data.get("credits", {}).get("crew", [])
        if c.get("job") == "Director" and c.get("name")
    ]
    if directors:
        out["director"] = ", ".join(directors[:3])

    # Géneros desde TMDb (vienen en inglés con language=en-US). Traducimos
    # los comunes al español y dejamos máximo 2 para no saturar la columna.
    TMDB_GENRE_ES = {
        "Action": "Acción", "Adventure": "Aventura", "Animation": "Animación",
        "Comedy": "Comedia", "Crime": "Crimen", "Documentary": "Documental",
        "Drama": "Drama", "Family": "Familiar", "Fantasy": "Fantasía",
        "History": "Historia", "Horror": "Terror", "Music": "Música",
        "Mystery": "Misterio", "Romance": "Romance",
        "Science Fiction": "Ciencia ficción", "TV Movie": "TV",
        "Thriller": "Thriller", "War": "Bélica", "Western": "Western",
    }
    genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]
    if genres:
        out["genre"] = ", ".join(TMDB_GENRE_ES.get(g, g) for g in genres[:2])

    # Title en español oficial — preferimos es-AR > es-ES > es-MX > es genérico
    title_es = ""
    priority = ["AR", "ES", "MX", "CL", "UY"]
    by_iso: dict[str, str] = {}
    for tr in data.get("translations", {}).get("translations", []):
        if tr.get("iso_639_1") != "es":
            continue
        title = (tr.get("data") or {}).get("title", "").strip()
        if title:
            by_iso[tr.get("iso_3166_1", "")] = title
    for code in priority:
        if code in by_iso:
            title_es = by_iso[code]
            break
    if not title_es and by_iso:
        title_es = next(iter(by_iso.values()))
    if title_es:
        out["title_es"] = title_es
    return out


def fill_meta_from_tmdb(
    meta: dict,
    title: str,
    hint_year: Optional[int],
    hint_original: str,
    hint_director: str,
) -> dict:
    """
    Si a `meta` le faltan duration/country/director, los completa via TMDb.
    Requiere TMDB_API_KEY o TMDB_READ_ACCESS_TOKEN. Sin credencial, retorna meta sin tocar.
    Valida match con hint_year (±2) y hint_director (overlap de palabras).
    """
    # Disparamos TMDb si falta algún campo crítico O si todavía no tenemos
    # title_es (queremos siempre el título oficial en español si existe).
    has_all = (
        meta.get("duration") and meta.get("country") and meta.get("director")
        and meta.get("title_es")
    )
    if has_all:
        return meta
    if not _tmdb_credential()[0]:
        return meta

    queries: list[tuple[str, Optional[int]]] = []
    if hint_original:
        queries.append((hint_original, hint_year))
    queries.append((title, hint_year))
    if hint_year:
        queries.append((title, None))

    seen_ids: set[int] = set()
    for q, y in queries:
        for cand in tmdb_search_movie(q, y):
            mid = cand.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            cand_year = cand.get("year")
            if hint_year and cand_year and abs(int(cand_year) - int(hint_year)) > 2:
                continue
            tmeta = fetch_tmdb_movie_meta(mid)
            if not tmeta:
                continue
            if hint_year and tmeta.get("year"):
                if abs(int(tmeta["year"]) - int(hint_year)) > 2:
                    continue
            if hint_director and tmeta.get("director"):
                if not _name_overlap(hint_director, tmeta["director"]):
                    continue
            for f in ("director", "country", "year", "duration", "title_en", "title_es", "original_title", "genre"):
                if not meta.get(f) and tmeta.get(f):
                    meta[f] = tmeta[f]
            if (meta.get("duration") and meta.get("country") and meta.get("director")
                    and meta.get("title_es")):
                return meta
    return meta


# Alias para callers internos
fill_meta_from_external = fill_meta_from_tmdb


def letterboxd_url_from_imdb(tt: str) -> Optional[str]:
    """
    LB acepta /imdb/ttXXXXXX/ y redirige a la película. Devuelve la URL final
    (https://letterboxd.com/film/SLUG/) o None.
    """
    url = f"https://letterboxd.com/imdb/{tt}/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        final = resp.url
        if "/film/" in final:
            return final.rstrip("/") + "/"
    except Exception:
        pass
    return None


# Throttle para DDG — la API HTML rate-limita rápido si pegamos consecutivo
_ddg_last_call = 0.0


def search_ddg_letterboxd(query: str, min_delay: float = 4.0) -> list[str]:
    """
    Busca en DuckDuckGo HTML y devuelve URLs letterboxd.com/film/SLUG/ de los
    primeros resultados. Aplica throttle para evitar bloqueo.
    """
    global _ddg_last_call
    import time, urllib.parse
    elapsed = time.monotonic() - _ddg_last_call
    if elapsed < min_delay:
        time.sleep(min_delay - elapsed)
    _ddg_last_call = time.monotonic()

    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except Exception:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "uddg=" in h:
            m = re.search(r"uddg=([^&]+)", h)
            if m:
                decoded = urllib.parse.unquote(m.group(1))
                mm = re.search(r"(https?://letterboxd\.com/film/[^/&?#]+/?)", decoded)
                if mm:
                    u = mm.group(1).rstrip("/") + "/"
                    if u not in urls:
                        urls.append(u)
        else:
            mm = re.search(r"(https?://letterboxd\.com/film/[^/&?#]+/?)", h)
            if mm:
                u = mm.group(1).rstrip("/") + "/"
                if u not in urls:
                    urls.append(u)
    return urls[:5]


async def enrich_title(
    title: str,
    page: "Page",
    cache: LetterboxdCache,
    delay: float = 1.0,
    hint_year: Optional[int] = None,
    hint_director: str = "",
    hint_original: str = "",
    hint_duration: Optional[int] = None,
) -> dict:
    """
    Dado un título y, opcionalmente, hints (año, director, título original) que el
    cine ya scrapeó, devuelve metadatos de Letterboxd. Usa caché y valida contra
    los hints para descartar matches incorrectos.

    Estrategia:
      1. Slug directo del título original (si hay) → fetch + validar
      2. Slug con `-YEAR` (si hay año) → fetch + validar
      3. Slug del título local → fetch + validar
      4. Letterboxd internal search → fetch + validar
      5. DuckDuckGo (con throttle) `letterboxd <title> <director>` → fetch + validar
      6. Si nada validó pero la búsqueda interna devolvió SOMETHING (sin hints),
         aceptarlo como mejor esfuerzo.
    """
    if is_non_film(title):
        return _empty_meta(title)

    # Key del cache scoped por año: dos películas homónimas en cartel al mismo
    # tiempo (ej. "Obsesión" de Visconti en Lugones y la de Curry Barker en
    # los comerciales) no deben pelear por el mismo slot — antes cada corrida
    # las re-enriquecía y la última pisaba a la otra. Sin año, key plana
    # (compatible con el cache legacy).
    cache_key = f"{title}|{hint_year}" if hint_year else title

    # Cache hit: solo lo devolvemos si valida contra los hints actuales.
    # Probamos la key con año y la legacy (title solo) — si la legacy valida,
    # la migramos a la key nueva. Si los hints cambiaron, re-enrich.
    for k in ([cache_key, title] if cache_key != title else [title]):
        if not cache.has(k):
            continue
        cached = cache.get(k)
        if not cached.get("url"):
            # Empty cached → re-intentar siempre por si la red estaba caída
            continue
        if _validate_meta(cached, hint_year, hint_director, hint_duration):
            # Auto-backfill de campos nuevos (ej. genre se agregó al parser
            # después de muchas entries estar cacheadas). Si el cached tiene
            # URL pero le falta genre, re-fetch sólo para completar el campo.
            if not cached.get("genre"):
                s = fetch_film_page(cached["url"])
                fresh = parse_film_soup(s, cached["url"]) if s else None
                if fresh and fresh.get("genre"):
                    cached["genre"] = fresh["genre"]
            cache.set(cache_key, cached)
            return cached
        # else: la entry cacheada NO matchea hints actuales → probar la otra
        # key o re-enrich

    search_title = title.title() if title == title.upper() else title
    candidates: list[str] = []

    def _try_url(u: str) -> Optional[dict]:
        s = fetch_film_page(u)
        return parse_film_soup(s, u) if s else None

    def _accept(m: dict) -> dict:
        """Antes de aceptar un match: completar campos faltantes desde IMDb."""
        m = fill_meta_from_external(m, title, hint_year, hint_original, hint_director)
        cache.set(cache_key, m)
        return m

    # 1. slug del título original (si lo tenemos)
    if hint_original:
        candidates.append(f"https://letterboxd.com/film/{slugify(hint_original)}/")
        if hint_year:
            candidates.append(f"https://letterboxd.com/film/{slugify(hint_original)}-{hint_year}/")

    # 2. slug del título local + año
    base_slug = slugify(search_title)
    if hint_year:
        candidates.append(f"https://letterboxd.com/film/{base_slug}-{hint_year}/")
    candidates.append(f"https://letterboxd.com/film/{base_slug}/")

    fallback_meta: Optional[dict] = None  # mejor esfuerzo si nada valida

    for u in candidates:
        m = _try_url(u)
        if not m:
            continue
        if _validate_meta(m, hint_year, hint_director, hint_duration):
            return _accept(m)
        fallback_meta = fallback_meta or m

    # 4. Letterboxd internal search — devuelve TODOS los matches, validamos cada uno
    # OJO: agregar año al query rompe la búsqueda interna; usar sólo el título
    await asyncio.sleep(delay)
    search_q = hint_original or search_title
    try:
        from urllib.parse import quote_plus
        await page.goto(
            f"https://letterboxd.com/search/films/{quote_plus(search_q)}/",
            wait_until="domcontentloaded", timeout=20000,
        )
        await page.wait_for_timeout(1500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        seen_hrefs: list[str] = []
        for a in soup.find_all("a", href=re.compile(r"^/film/")):
            href = a["href"]
            if re.match(r"^/film/[^/]+/?$", href) and href not in seen_hrefs:
                seen_hrefs.append(href)
                if len(seen_hrefs) >= 5:
                    break
        for href in seen_hrefs:
            u = "https://letterboxd.com" + href.rstrip("/") + "/"
            await asyncio.sleep(0.5)
            m = _try_url(u)
            if not m:
                continue
            if _validate_meta(m, hint_year, hint_director, hint_duration):
                return _accept(m)
            fallback_meta = fallback_meta or m
    except Exception:
        pass

    # 5. IMDB suggestion API → LB via /imdb/tt redirect.
    # IMDB matchea mejor que LB para títulos en español traducidos y pelis
    # nuevas. La API de suggestions sólo acepta el título (NO funciona con
    # director appended). Probamos título original si lo tenemos, luego local.
    imdb_queries: list[str] = []
    if hint_original:
        imdb_queries.append(f"{hint_original} {hint_year}" if hint_year else hint_original)
        imdb_queries.append(hint_original)
    imdb_queries.append(f"{search_title} {hint_year}" if hint_year else search_title)
    if hint_year:
        imdb_queries.append(search_title)

    seen_tt: set[str] = set()
    for q in imdb_queries:
        candidates_imdb = list(imdb_suggest(q))
        # Sin hint_year, preferir las pelis MÁS NUEVAS (estrenos típicos en Lorca/Cacodelphia)
        if not hint_year:
            candidates_imdb.sort(key=lambda c: c.get("year") or 0, reverse=True)
        for cand in candidates_imdb:
            if cand["tt"] in seen_tt:
                continue
            seen_tt.add(cand["tt"])
            cand_year = cand.get("year")
            # Filtros pre-fetch para evitar requests inútiles
            if hint_year and cand_year:
                try:
                    if abs(int(cand_year) - int(hint_year)) > 2:
                        continue
                except (TypeError, ValueError):
                    pass
            elif not hint_year and cand_year:
                # Sin hint, asumimos que la peli es estreno reciente: descartar
                # films viejos para evitar falsos positivos como
                # "Sueños de Oslo" → "Men Are from Mars..." (2014)
                try:
                    if int(cand_year) < 2020:
                        continue
                except (TypeError, ValueError):
                    pass
            lb_url = letterboxd_url_from_imdb(cand["tt"])
            if not lb_url:
                continue
            m = _try_url(lb_url)
            if not m:
                continue
            if _validate_meta(m, hint_year, hint_director, hint_duration):
                return _accept(m)
            fallback_meta = fallback_meta or m

    # 5bis. TMDb search → IMDb id → LB. Cubre títulos locales cuyo título
    # canónico en LB está en otro idioma (slug inadivinable) y que la
    # suggestion API de IMDb no matchea.
    for lb_url in tmdb_letterboxd_candidates(
        search_title, hint_original, hint_year, min_year_no_hint=_NO_HINT_MIN_YEAR,
    ):
        m = _try_url(lb_url)
        if not m:
            continue
        if _validate_meta(m, hint_year, hint_director, hint_duration):
            return _accept(m)
        fallback_meta = fallback_meta or m

    # 6. DuckDuckGo fallback (con throttle, último recurso)
    if hint_director:
        q = f"letterboxd {search_title} {hint_director}"
        for u in search_ddg_letterboxd(q):
            m = _try_url(u)
            if not m:
                continue
            if _validate_meta(m, hint_year, hint_director, hint_duration):
                return _accept(m)
            fallback_meta = fallback_meta or m

    # 6. Si no validamos nada pero teníamos algún match razonable y NO hay hints
    # estrictos, aceptarlo como mejor esfuerzo — PERO sólo si la duración no lo
    # contradice. Antes la duración se ignoraba acá, así que un match con
    # duración incompatible (peli homónima distinta) se colaba igual.
    fb_dur_ok = not (
        hint_duration and fallback_meta and fallback_meta.get("duration")
        and abs(int(fallback_meta["duration"]) - int(hint_duration)) > 5
    )
    # Sin hints, no aceptamos como mejor esfuerzo una peli claramente vieja
    # (homónimo equivocado en salas de estrenos).
    fb_recent_ok = not (
        not hint_year and not hint_director and fallback_meta and fallback_meta.get("year")
        and int(fallback_meta["year"]) < _NO_HINT_MIN_YEAR
    )
    if fallback_meta and not (hint_year or hint_director) and fb_dur_ok and fb_recent_ok:
        # Si IMDb puede completar campos faltantes, lo intentamos
        fallback_meta = fill_meta_from_external(
            fallback_meta, title, hint_year, hint_original, hint_director,
        )
        cache.set(cache_key, fallback_meta)
        return fallback_meta

    # 7. Último intento: rellenar empty meta directo desde IMDb (sin LB)
    empty = _empty_meta(title)
    empty = fill_meta_from_external(empty, title, hint_year, hint_original, hint_director)
    cache.set(cache_key, empty)
    return empty


def _empty_meta(title: str) -> dict:
    return {
        "url": "",
        "title_en": title,
        "director": "",
        "country": "",
        "year": None,
        "duration": None,
    }
