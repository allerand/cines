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
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

# Sin hints (año/director) para desambiguar, rechazamos películas más viejas que
# este corte: casi siempre son homónimos equivocados en salas que programan
# estrenos (Cacodelphia, Lorca). Ej.: "Familia" (Costabile, 2024) matcheaba con
# una "Familia" de 1992.
_NO_HINT_MIN_YEAR = date.today().year - 8

# Sin hints, y con un título que no coincide con ninguno de los de la película
# —lo normal en un estreno: 'El gran falsificador' es The Money Maker y
# Letterboxd no conoce el título argentino—, sólo aceptamos estrenos de verdad.
# Una película de hace cinco años con otro nombre ya no es el título local de un
# estreno sino otra película: 'Frida, naturaleza viva' (Leduc, 1983) salía como
# 'Natura Bizia' (2021).
_NO_HINT_MIN_YEAR_DISTINTO = date.today().year - 2

# Una película de este año o del anterior está en cartel: entre varias que se
# llaman igual, en una sala de estrenos es ésa (ver _decidir_sin_hints).
_ESTRENO_DESDE = date.today().year - 1

# Títulos que el enrichment dejó sin ficha a propósito, con el motivo. run.py
# los lista al final de la corrida para completarlos con un override si hace
# falta, en vez de adivinar.
SIN_FICHA: dict[str, str] = {}

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

    # Título original y alternativos ("Alternative Titles" en la pestaña de
    # detalles): con ellos se sabe si la película se llama de verdad como la
    # anuncia el cine —Oldboy figura también como 'Old Boy'; Old Suffolk Boy,
    # no—. Sólo los de alfabeto latino, que son los que se pueden comparar. No
    # van al caché (ver _para_cache): son muchos y sólo sirven para validar.
    titulos = [title_en]
    original = soup.find("h2", class_="originalname")
    if original:
        titulos.append(original.get_text(strip=True))
    for h3 in soup.find_all("h3"):
        if h3.get_text(strip=True).lower().startswith("alternative title"):
            lista = h3.find_next_sibling("div")
            if lista:
                titulos += lista.get_text(" ", strip=True).split(", ")
            break
    titulos = [t for t in dict.fromkeys(t.strip() for t in titulos)
               if t and re.search(r"[a-z]", _ascii(t))]

    return {
        "url": url,
        "title_en": title_en,
        "director": director,
        "country": country,
        "year": year,
        "duration": duration,
        "genre": genre,
        "titulos": titulos,
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


def _ascii(s: str) -> str:
    """Minúsculas y sin acentos: 'Fazáns' → 'fazans'."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower()


def _lev(a: str, b: str) -> int:
    """Distancia de edición entre dos palabras."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _misma_palabra(a: str, b: str) -> bool:
    """Iguales, o con un error de tipeo: las fuentes escriben mal los apellidos
    ('Frenkel' por Frankel, 'Fanzas' por Fazáns) y no por eso es otra persona."""
    if a == b:
        return True
    n = min(len(a), len(b))
    return n >= 5 and _lev(a, b) <= (1 if n < 6 else 2)


_PARTICULAS = {"de", "del", "la", "las", "los", "van", "von", "da", "di", "du", "le"}


def _name_overlap(a: str, b: str) -> bool:
    """True si algún director de `a` y alguno de `b` comparten el apellido.

    Antes alcanzaba con cualquier palabra en común, y la que más se repite es
    el nombre de pila: 'Joaquín Pereyra' validaba un corto de 'Joaquín Farías
    Caamaño' y la función salía con el Letterboxd de otra película. Ahora la
    palabra compartida tiene que ser la última de alguno de los dos nombres —el
    apellido, o el nombre en el orden coreano: 'Park Chan-wook' y 'Chan-wook
    Park' coinciden igual—, con tolerancia a un error de tipeo.
    """
    def nombres(s: str) -> list[list[str]]:
        out = []
        for n in re.split(r",|;|&|\s+y\s+|\s+and\s+", s or ""):
            toks = [w for w in re.split(r"[\s.\-]+", _ascii(n))
                    if len(w) > 1 and w not in _PARTICULAS]
            if toks:
                out.append(toks)
        return out
    for x in nombres(a):
        for y in nombres(b):
            for tx in x:
                for ty in y:
                    if (tx == x[-1] or ty == y[-1]) and _misma_palabra(tx, ty):
                        return True
    return False


# Conectores que no cambian un título ('Romeo & Ofelia' = 'Romeo y Ofelia') y
# artículos, que no cuentan para decidir si un título contiene a otro.
_CONECTORES = {"y", "and", "e", "et", "und"}
_ARTICULOS = _CONECTORES | {"el", "la", "los", "las", "un", "una", "de", "del", "en",
                            "the", "a", "an", "of", "le", "les", "des", "du", "il",
                            "lo", "o", "da", "do", "das", "dos", "di"}


def _norm_titulo(t: str) -> str:
    """'Old Boy' y 'Oldboy' → 'oldboy'."""
    return "".join(w for w in re.split(r"[^a-z0-9]+", _ascii(t)) if w and w not in _CONECTORES)


def _variantes_titulo(t: str, separadores: tuple = (":", " - ", " – ")) -> set[str]:
    """El título y sus formas cortas: sin subtítulo ('Oldboy: Cinco días para
    vengarse' → Oldboy) y con o sin lo que va entre paréntesis ('Moonrise
    (Noche sin luna)'), salvo que sea un año.

    Al título del cine se le corta sólo lo que va después de un guion, que es
    donde agrega cosas ('Zona Cero - Colony', 'Backrooms - Versión
    extendida'); los dos puntos son parte del nombre, y 'Spider-Man: Un día
    nuevo' sin ellos es 'Spider-Man', que es otra película."""
    t = t or ""
    vs = {t}
    for sep in separadores:
        if sep in t:
            vs.add(t.split(sep)[0])
    m = re.search(r"\(([^)]+)\)", t)
    if m:
        vs.add(re.sub(r"\([^)]*\)", "", t))
        if not re.fullmatch(r"\s*(19|20)\d{2}\s*", m.group(1)):
            vs.add(m.group(1))
    return {_norm_titulo(v) for v in vs} - {""}


def _palabras(t: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", _ascii(t)) if w and w not in _ARTICULOS}


def clase_titulo(titulos_fuente: list[str], titulos_film: list[str]) -> str:
    """Compara cómo anuncia la película el cine con los títulos que tiene.

      "exacto"   coincide con el título, el original o algún alternativo.
      "pisado"   la película tiene todas las palabras del cine y además otras:
                 'Old Boy' → 'Old Suffolk Boy', 'Tu rostro' → 'Tengo miedo de
                 olvidar tu rostro', 'Vértigo' → 'Vértigo 2: Punto muerto'. Es
                 lo que devuelve un buscador cuando no tiene la película —otra
                 que se llama parecido—; una traducción no se parece así. Si el
                 cine cortó un título largo ('Tadeo el explorador y la
                 lámpara…'), la película empieza igual y eso no cuenta.
      "distinto" ninguna de las dos. Es lo normal en un estreno cuyo título
                 argentino Letterboxd no conoce ('El gran falsificador' es The
                 Money Maker), así que por sí solo no dice nada.
    """
    fuente = [t for t in titulos_fuente if t]
    film = [t for t in titulos_film if t]
    vf: set[str] = set()
    for t in fuente:
        vf |= _variantes_titulo(t, separadores=(" - ", " – "))
    if any(vf & _variantes_titulo(t) for t in film):
        return "exacto"
    for tf in fuente:
        pw = _palabras(tf)
        for t in film:
            if pw and pw < _palabras(t):
                cortado = len(pw) >= 3 and _norm_titulo(t).startswith(_norm_titulo(tf))
                if not cortado:
                    return "pisado"
    return "distinto"


def _validate_meta(
    meta: dict,
    hint_year: Optional[int],
    hint_director: str,
    hint_duration: Optional[int] = None,
    clase: Optional[str] = None,
) -> bool:
    """
    Decide si el match de Letterboxd es coherente con la metadata del cine.
      - Si hint_year ±2 difiere del LB year → rechazar
      - Si hint_director y LB director no comparten el apellido → rechazar
      - Si meta no trae director ni year, no podemos validar → rechazar también
        cuando hay hint_director (mejor empty que wrong)
      - Si hint_duration ±5 difiere del LB duration → rechazar
      - Sin director que lo confirme, un título "pisado" es otra película que
        se llama parecido → rechazar. `clase` es la de clase_titulo; sin ella
        no se mira el título.
      - Sin director ni año, la película tiene que tener año —si no, no hay con
        qué descartar un homónimo viejo: así pasó 'Old Suffolk Boy', 1936 y sin
        año en Letterboxd, por 'Old Boy'—, no puede ser más vieja que
        _NO_HINT_MIN_YEAR y, si el título no coincide, tampoco que
        _NO_HINT_MIN_YEAR_DISTINTO. Esas funciones las decide
        _decidir_sin_hints; esto queda de red por si una llega por otro lado.
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
    if not hint_director and clase == "pisado":
        return False
    if not hint_year and not hint_director:
        year = meta.get("year")
        if not year or int(year) < _NO_HINT_MIN_YEAR:
            return False
        if clase == "distinto" and int(year) < _NO_HINT_MIN_YEAR_DISTINTO:
            return False
    return True


def _clase_de(meta: dict, title: str, hint_original: str = "") -> Optional[str]:
    """clase_titulo de una ficha. Las del caché no guardan los títulos
    alternativos, así que la primera vez se vuelve a leer la página y la clase
    queda anotada en la ficha."""
    if meta.get("clase_titulo"):
        return meta["clase_titulo"]
    titulos = meta.get("titulos")
    if titulos is None and meta.get("url"):
        s = fetch_film_page(meta["url"])
        titulos = ((parse_film_soup(s, meta["url"]) if s else None) or {}).get("titulos")
    if not titulos:
        return None
    meta["clase_titulo"] = clase_titulo([title, hint_original], titulos)
    return meta["clase_titulo"]


def _para_cache(meta: dict) -> dict:
    """La ficha sin los títulos alternativos: ocupan y sólo sirven para
    validar, y la clase ya quedó calculada."""
    return {k: v for k, v in meta.items() if k != "titulos"}


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
    data = _tmdb_request(f"/movie/{movie_id}", {"append_to_response": "credits,translations,alternative_titles", "language": "en-US"})
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
    # Todos los títulos de la película, para compararlos con el del cine (ver
    # clase_titulo): traducciones y alternativos de cada país.
    titulos = [data.get("title") or "", data.get("original_title") or ""]
    for tr in data.get("translations", {}).get("translations", []):
        title = ((tr.get("data") or {}).get("title") or "").strip()
        if title:
            titulos.append(title)
        if tr.get("iso_639_1") != "es":
            continue
        if title:
            by_iso[tr.get("iso_3166_1", "")] = title
    for alt in (data.get("alternative_titles") or {}).get("titles", []):
        titulos.append((alt.get("title") or "").strip())
    out["titulos"] = [t for t in dict.fromkeys(titulos) if t and re.search(r"[a-z]", _ascii(t))]
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
    hint_duration: Optional[int] = None,
) -> dict:
    """
    Si a `meta` le faltan duration/country/director, los completa via TMDb.
    Requiere TMDB_API_KEY o TMDB_READ_ACCESS_TOKEN. Sin credencial, retorna meta sin tocar.
    Valida match con hint_year (±2) y hint_director (apellido en común).

    Completa desde UNA sola película, la primera que pasa los filtros. Antes
    seguía mirando candidatos mientras faltara algún campo y cada uno ponía lo
    suyo: el país de una, el título en español de otra.
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

    # Validamos contra lo que YA sabemos de la película — normalmente porque lo
    # trajo Letterboxd — y no sólo contra los hints de la fuente. Los hints
    # vienen vacíos seguido (no todos los cines publican director o año), y sin
    # ellos cualquier resultado de TMDb pasaba el filtro. Así es como el título
    # en español de OTRA película termina siendo el título que se muestra.
    check_year = hint_year or meta.get("year")
    check_director = hint_director or meta.get("director")

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
            if check_year and cand_year and abs(int(cand_year) - int(check_year)) > 2:
                continue
            tmeta = fetch_tmdb_movie_meta(mid)
            if not tmeta:
                continue
            if check_year and tmeta.get("year"):
                if abs(int(tmeta["year"]) - int(check_year)) > 2:
                    continue
            if check_director:
                # Sabiendo de quién es, el candidato tiene que decirlo. Uno que
                # apenas no lo contradice (TMDb sin director) no alcanza: pondría
                # el país, la duración o el título de lo que puede ser otra
                # película, y un título ajeno es lo primero que ve la gente.
                if not (tmeta.get("director")
                        and _name_overlap(check_director, tmeta["director"])):
                    continue
            else:
                # Sin director con qué confirmar, TMDb es la única fuente: al
                # menos que no sea otra película que se llama parecido ('An Old
                # Fashioned Boy' por Old Boy), que la duración no la contradiga
                # y, si tampoco hay año, que no sea un homónimo viejo.
                if clase_titulo([title, hint_original], tmeta.get("titulos", [])) == "pisado":
                    continue
                if (hint_duration and tmeta.get("duration")
                        and abs(int(tmeta["duration"]) - int(hint_duration)) > 5):
                    continue
                if not check_year and (not tmeta.get("year")
                                       or int(tmeta["year"]) < _NO_HINT_MIN_YEAR):
                    continue

            for f in ("director", "country", "year", "duration", "genre",
                      "title_en", "title_es", "original_title"):
                if not meta.get(f) and tmeta.get(f):
                    meta[f] = tmeta[f]
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
    Sin director ni año va por _enrich_sin_hints, que junta los candidatos de
    todas las fuentes y elige sólo si uno se destaca.
    """
    if is_non_film(title):
        return _empty_meta(title)

    # Un año entre paréntesis al final es un dato de la fuente, no parte del
    # nombre: 'Moana (2026)' separa la de acción real de la animada de 2016,
    # que con el título solo empatarían.
    if not hint_year:
        m_anio = re.search(r"\(((?:19|20)\d{2})\)\s*$", title)
        if m_anio:
            hint_year = int(m_anio.group(1))

    # Sin director ni año, validar candidato por candidato no alcanza.
    if not hint_year and not hint_director:
        return await _enrich_sin_hints(title, page, cache, delay, hint_original, hint_duration)

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
        if _validate_meta(cached, hint_year, hint_director, hint_duration,
                          None if hint_director else _clase_de(cached, title, hint_original)):
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

    def _clase(m: dict) -> Optional[str]:
        # Con un director que confirme, el título no hace falta mirarlo.
        return None if hint_director else _clase_de(m, title, hint_original)

    def _accept(m: dict) -> dict:
        """Antes de aceptar un match: completar campos faltantes desde TMDb."""
        m = fill_meta_from_external(_para_cache(m), title, hint_year, hint_original,
                                    hint_director, hint_duration)
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

    for u in candidates:
        m = _try_url(u)
        if not m:
            continue
        if _validate_meta(m, hint_year, hint_director, hint_duration, _clase(m)):
            return _accept(m)

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
            if _validate_meta(m, hint_year, hint_director, hint_duration, _clase(m)):
                return _accept(m)
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
            if _validate_meta(m, hint_year, hint_director, hint_duration, _clase(m)):
                return _accept(m)

    # 5bis. TMDb search → IMDb id → LB. Cubre títulos locales cuyo título
    # canónico en LB está en otro idioma (slug inadivinable) y que la
    # suggestion API de IMDb no matchea.
    for lb_url in tmdb_letterboxd_candidates(
        search_title, hint_original, hint_year, min_year_no_hint=_NO_HINT_MIN_YEAR,
    ):
        m = _try_url(lb_url)
        if not m:
            continue
        if _validate_meta(m, hint_year, hint_director, hint_duration, _clase(m)):
            return _accept(m)

    # 6. DuckDuckGo fallback (con throttle, último recurso)
    if hint_director:
        q = f"letterboxd {search_title} {hint_director}"
        for u in search_ddg_letterboxd(q):
            m = _try_url(u)
            if not m:
                continue
            if _validate_meta(m, hint_year, hint_director, hint_duration, _clase(m)):
                return _accept(m)

    # (Acá había un "mejor esfuerzo" que, sin hints, aceptaba el primer
    # candidato que NO había validado. Esas funciones ahora van por
    # _enrich_sin_hints; con hints, un candidato que no valida es otra película.)

    # 7. Último intento: rellenar empty meta directo desde TMDb (sin LB)
    empty = _empty_meta(title)
    empty = fill_meta_from_external(empty, title, hint_year, hint_original, hint_director,
                                    hint_duration)
    cache.set(cache_key, empty)
    return empty


# Tope de candidatos a mirar sin hints: los primeros de cada buscador alcanzan
# para saber si hay homónimos, y cada uno cuesta dos o tres requests.
_MAX_CANDIDATOS = 10


def _mismo_film(a: dict, b: dict) -> bool:
    return (a.get("year") == b.get("year")
            and _norm_titulo(a.get("title_en", "")) == _norm_titulo(b.get("title_en", "")))


def _lista(ms: list[dict]) -> str:
    return ", ".join(f"{m.get('title_en')} ({m.get('year')})" for m in ms[:4])


def _decidir_sin_hints(
    fuente: list[str],
    hint_duration: Optional[int],
    candidatos: list[tuple[dict, str]],
    homonimo_fuera: bool = False,
) -> tuple[Optional[dict], str]:
    """
    Elige entre los candidatos de una función que no trae director ni año.
    `fuente` son los títulos con que la anuncia el cine; `candidatos`, pares
    (ficha, vía) con vía "slug", "busqueda" (Letterboxd), "imdb" o "tmdb".
    Devuelve (ficha elegida o None, motivo).

    Sólo elige si uno se destaca sin discusión:
      1. Afuera los que no tienen año, los que contradicen la duración y los de
         título "pisado" (ver clase_titulo).
      2. Si hay películas que se llaman exactamente así:
         - con la duración de la función, gana la única que tiene duración y
           coincide, sea del año que sea: Old Boy de 119 min es Oldboy (2003,
           120 min) y no la 'Old Boy' de 2018;
         - si no, sólo si es una sola y no es vieja;
         - si son varias (con o sin duración), sólo si la más nueva es un
           estreno (_ESTRENO_DESDE) y no empata con otra del mismo año: 'La
           Odisea' es la de Nolan y no la miniserie de 1997; 'Código:
           Venganza', Mutiny (2026) y no Tin Soldier (2025), que en su momento
           se estrenó con el mismo nombre. Si no, no hay forma de saber cuál: 'Vértigo' es la de
           Hitchcock, una de 2019 y también 'Fall' (2022), que en castellano se
           llamó así. Lo del estreno es una apuesta de sala comercial: en un
           ciclo de repertorio sin fichas pierde ('Los amos del tiempo' de
           Laloux contra una mexicana de 2025), pero sin ella las películas
           más vistas de los multiplex quedarían sin ficha.
      3. Si ninguna se llama así, puede ser el título local de un estreno: la
         primera que proponen IMDb o TMDb —que conocen los títulos de cada
         país— siempre que sea de los últimos dos años. No las que salen de
         adivinar el slug o de la búsqueda de Letterboxd: ahí un título que no
         coincide es otra película, no una traducción. Y tampoco si existe
         una película que se llama exactamente así, aunque no sirva porque
         dura otra cosa o no está en Letterboxd (`homonimo_fuera`: la vio
         IMDb): entonces el título es de ésa, y la otra sólo se le parece. El
         'Islandia' de Cacodelphia es un documental que Letterboxd no tiene;
         'Spider Island' sí, y dura 95 minutos contra 94.
    """
    exactos: list[dict] = []
    traducidos: list[dict] = []
    homonimos: list[dict] = []   # se llaman así pero no sirven
    for m, via in candidatos:
        clase = clase_titulo(fuente, m.get("titulos") or [m.get("title_en", "")])
        m["clase_titulo"] = clase
        if not m.get("year") or (hint_duration and m.get("duration")
                                 and abs(int(m["duration"]) - int(hint_duration)) > 5):
            if clase == "exacto":
                homonimos.append(m)
            continue
        if clase == "exacto":
            lista = exactos
        elif clase == "distinto" and via in ("imdb", "tmdb"):
            lista = traducidos
        else:
            continue
        if not any(_mismo_film(m, otro) for otro in lista):
            lista.append(m)

    def unico_estreno(ms: list[dict]) -> Optional[dict]:
        """La más nueva, si es un estreno y no empata con otra del mismo año."""
        anio = max(int(m["year"]) for m in ms)
        nuevas = [m for m in ms if int(m["year"]) == anio]
        return nuevas[0] if anio >= _ESTRENO_DESDE and len(nuevas) == 1 else None

    if exactos:
        if hint_duration:
            con_duracion = [m for m in exactos if m.get("duration")]
            if len(con_duracion) == 1:
                return con_duracion[0], "título y duración"
            if len(con_duracion) > 1:
                if unico_estreno(con_duracion):
                    return unico_estreno(con_duracion), "el único estreno entre varias que se llaman así"
                return None, f"varias se llaman así y duran lo mismo: {_lista(con_duracion)}"
        if len(exactos) > 1:
            if unico_estreno(exactos):
                return unico_estreno(exactos), "el único estreno entre varias que se llaman así"
            return None, f"varias se llaman así: {_lista(exactos)}"
        m = exactos[0]
        if int(m["year"]) >= _NO_HINT_MIN_YEAR:
            return m, "título"
        return None, f"la única que se llama así es {_lista([m])}, y puede ser otra"

    if traducidos and (homonimos or homonimo_fuera):
        cuales = f": {_lista(homonimos)}" if homonimos else " fuera de Letterboxd"
        return None, (f"hay películas que se llaman así{cuales}; "
                      f"{_lista(traducidos[:1])} sólo se le parece")
    for m in traducidos:
        if int(m["year"]) >= _NO_HINT_MIN_YEAR_DISTINTO:
            return m, "título local de un estreno"
    if traducidos:
        return None, f"ninguna se llama así y lo que aparece no es estreno: {_lista(traducidos)}"
    return None, "ninguna película se llama así"


def _tmdb_candidatos(title: str, hint_original: str) -> list[tuple[dict, str]]:
    """Fichas de TMDb, para cuando Letterboxd no tiene nada (una película
    argentina chica, un estreno que todavía no cargaron)."""
    if not _tmdb_credential()[0]:
        return []
    out: list[tuple[dict, str]] = []
    vistos: set[int] = set()
    for q in dict.fromkeys(x for x in (hint_original, title) if x):
        for cand in tmdb_search_movie(q):
            if not cand.get("id") or cand["id"] in vistos:
                continue
            vistos.add(cand["id"])
            tmeta = fetch_tmdb_movie_meta(cand["id"])
            if tmeta:
                out.append((tmeta, "tmdb"))
    return out


async def _enrich_sin_hints(
    title: str,
    page: "Page",
    cache: LetterboxdCache,
    delay: float,
    hint_original: str,
    hint_duration: Optional[int],
) -> dict:
    """
    Enrichment de las funciones que llegan sin director ni año —Lorca,
    Multiplex, los comerciales de La Nación, Cacodelphia—: el título, a lo sumo
    con la duración, es todo lo que hay.

    Con director o año, cada candidato se valida contra el dato y gana el
    primero que coincide. Sin ellos no hay contra qué validar, y "el primero"
    era el que devolvía primero algún buscador: así salieron 'Old Suffolk Boy'
    (1936) por Old Boy, 'Spider Island' por el documental 'Islandia' y 'Fall 2'
    por el Vértigo de Hitchcock. Acá se juntan los candidatos de todas las
    fuentes y se elige sólo si uno se destaca (_decidir_sin_hints). Si no, la
    función queda sin ficha y el motivo va a SIN_FICHA: una fila vacía se nota
    y se completa; la ficha de otra película se publica, se postea y nadie se
    entera.
    """
    cached = cache.get(title) if cache.has(title) else None
    if cached and cached.get("sin_hints"):
        # Una decisión de esta misma lógica: vale mientras la duración no la
        # contradiga.
        if not (hint_duration and cached.get("duration")
                and abs(int(cached["duration"]) - int(hint_duration)) > 5):
            return cached
    elif cached and cached.get("sin_ficha"):
        # Quedó sin ficha porque no se pudo elegir. Se vuelve a intentar a los
        # tres días, o antes si ahora llega una duración que antes no (la ficha
        # de Cacodelphia a veces no se puede leer y la duración no viene).
        reciente = cached.get("fecha", "") >= (date.today() - timedelta(days=3)).isoformat()
        if reciente and cached.get("con_duracion") == bool(hint_duration):
            SIN_FICHA[title] = cached["sin_ficha"]
            return cached

    search_title = title.title() if title == title.upper() else title
    fuente = [title, hint_original]
    candidatos: list[tuple[dict, str]] = []
    urls: set[str] = set()

    def probar(u: Optional[str], via: str) -> None:
        if not u or u in urls or len(candidatos) >= _MAX_CANDIDATOS:
            return
        urls.add(u)
        s = fetch_film_page(u)
        m = parse_film_soup(s, u) if s else None
        if m:
            candidatos.append((m, via))

    # 1. El slug que saldría del título (y del original, si lo hay).
    if hint_original:
        probar(f"https://letterboxd.com/film/{slugify(hint_original)}/", "slug")
    probar(f"https://letterboxd.com/film/{slugify(search_title)}/", "slug")

    # 2. La búsqueda de Letterboxd.
    await asyncio.sleep(delay)
    try:
        from urllib.parse import quote_plus
        await page.goto(
            f"https://letterboxd.com/search/films/{quote_plus(hint_original or search_title)}/",
            wait_until="domcontentloaded", timeout=20000,
        )
        await page.wait_for_timeout(1500)
        soup = BeautifulSoup(await page.content(), "html.parser")
        hrefs: list[str] = []
        for a in soup.find_all("a", href=re.compile(r"^/film/[^/]+/?$")):
            if a["href"] not in hrefs:
                hrefs.append(a["href"])
        for href in hrefs[:5]:
            probar("https://letterboxd.com" + href.rstrip("/") + "/", "busqueda")
    except Exception:
        pass

    # 3. IMDb, que conoce el título de cada país y encuentra la película aunque
    # el cine la anuncie en castellano. Van todos sus candidatos, también los
    # viejos: un homónimo que se llama igual es justamente lo que hace dudar.
    vistos_tt: set[str] = set()
    homonimo_fuera = False
    for q in dict.fromkeys(x for x in (hint_original, search_title) if x):
        for cand in imdb_suggest(q):
            # Que IMDb conozca una película con este mismo nombre ya dice algo,
            # esté o no en Letterboxd (ver _decidir_sin_hints).
            if clase_titulo(fuente, [cand.get("title", "")]) == "exacto":
                homonimo_fuera = True
            if cand["tt"] not in vistos_tt and len(candidatos) < _MAX_CANDIDATOS:
                vistos_tt.add(cand["tt"])
                probar(letterboxd_url_from_imdb(cand["tt"]), "imdb")

    # 4. TMDb, sólo si hasta acá no apareció nadie que se llame así ('Obsesión'
    # de Curry Barker: el slug está en inglés e IMDb no la encuentra).
    elegido, motivo = _decidir_sin_hints(fuente, hint_duration, candidatos, homonimo_fuera)
    if not elegido and not any(m.get("clase_titulo") == "exacto" for m, _ in candidatos):
        for u in tmdb_letterboxd_candidates(search_title, hint_original, None):
            probar(u, "tmdb")
        elegido, motivo = _decidir_sin_hints(fuente, hint_duration, candidatos, homonimo_fuera)

    # 5. Nada en Letterboxd: la ficha sale de TMDb, con el mismo criterio.
    if not elegido and not candidatos:
        elegido, motivo = _decidir_sin_hints(
            fuente, hint_duration, _tmdb_candidatos(search_title, hint_original), homonimo_fuera)

    if elegido and elegido.get("url"):
        # Lo que falte lo completa TMDb, que tiene que coincidir con el
        # director que dice Letterboxd.
        meta = fill_meta_from_external(_para_cache(elegido), title, None, hint_original, "")
    elif elegido:
        meta = _empty_meta(title)
        for f in ("director", "country", "year", "duration", "genre", "title_es", "original_title"):
            if elegido.get(f):
                meta[f] = elegido[f]
    else:
        meta = _empty_meta(title)
        SIN_FICHA[title] = motivo
        if candidatos:
            # Con candidatos en la mano y ninguno elegible, mañana la respuesta
            # va a ser la misma. Sin ninguno puede haber sido la red: se
            # reintenta en la próxima corrida.
            meta.update(sin_ficha=motivo, fecha=date.today().isoformat(),
                        con_duracion=bool(hint_duration))
        cache.set(title, meta)
        return meta
    meta["sin_hints"] = motivo
    cache.set(title, meta)
    return meta


def _empty_meta(title: str) -> dict:
    return {
        "url": "",
        "title_en": title,
        "director": "",
        "country": "",
        "year": None,
        "duration": None,
    }
