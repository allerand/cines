#!/usr/bin/env python3
"""
Orquestador principal del scraper de cines.

Uso:
    python run.py              # scrapedar + actualizar data/cartelera.json
    python run.py --serve      # scrapedar + levantar servidor web en :8080
    python run.py --semanas 3  # ampliar ventana de fechas
"""

import argparse
import asyncio
import http.server
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)

CARTELERA_JSON = DATA_DIR / "cartelera.json"
CACHE_JSON = DATA_DIR / "cache.json"
LB_OVERRIDES_JSON = DATA_DIR / "letterboxd_overrides.json"
METADATA_OVERRIDES_JSON = DATA_DIR / "metadata_overrides.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def run_scraper(semanas: int = 9, sin_proxy: bool = False) -> None:
    """`sin_proxy` saltea los cines que sólo se bajan por el proxy pago (CCK y
    Borges). Lo usa el pase de la tarde: los dos publican con semanas de
    anticipación, así que el de la madrugada alcanza, y cada corrida extra sale
    ~9 requests del plan. El scrape de la mañana los trae igual, y el merge
    conserva sus funciones futuras."""
    from scraper import (
        scrape_malba, scrape_lugones, scrape_cacodelphia,
        scrape_lorca, scrape_lumiton_agenda, scrape_cosmos,
        scrape_gaumont, scrape_cck, scrape_arthaus, scrape_museo_cine,
        scrape_ccr, scrape_imdb_then_lanacion, scrape_amorina, scrape_cea,
        scrape_filo, scrape_bn, scrape_cc25, scrape_ccd, scrape_cb,
        scrape_borges, scrape_bcn, scrape_agn, scrape_bellasartes,
        scrape_manual, descartar_manual,
        scrape_cinemark_hoyts, scrape_pena_sin_cadenas, scrape_multiplex,
        resumen_proxy,
    )
    # IMDb+Lanación se scrapea dentro del bloque async_playwright (necesita
    # browser para IMDb). Inicializamos vacío y se llena más abajo.
    lorca_screenings: list = []
    commercial_screenings: list = []

    print("🎬 Cine Lorca + Comerciales (IMDb primero, Lanación fallback)...")
    try:
        # placeholder — se ejecuta abajo dentro de async_playwright
        pass
    except Exception as e:
        print(f"error — {e}")
    except Exception as e:
        commercial_screenings = []
        print(f"error — {e}")

    print("🎬 Scrapeando Lumiton (York / Munro / Lumiton)...", end=" ", flush=True)
    try:
        lumiton_screenings = scrape_lumiton_agenda()
        from collections import Counter
        c = Counter(s.cine for s in lumiton_screenings)
        print(", ".join(f"{cine}: {n}" for cine, n in c.items()) or "0")
    except Exception as e:
        lumiton_screenings = []
        print(f"error — {e}")

    print("🎬 Scrapeando Cine Cosmos UBA...", end=" ", flush=True)
    try:
        cosmos_screenings = scrape_cosmos(semanas)
        print(f"{len(cosmos_screenings)} funciones")
    except Exception as e:
        cosmos_screenings = []
        print(f"error — {e}")

    print("🎬 Scrapeando Cine Gaumont...", end=" ", flush=True)
    try:
        gaumont_screenings = scrape_gaumont(semanas)
        print(f"{len(gaumont_screenings)} funciones")
    except Exception as e:
        gaumont_screenings = []
        print(f"error — {e}")

    print("🎬 Scrapeando CCK...", end=" ", flush=True)
    if sin_proxy:
        cck_screenings = []
        print("salteado (--sin-proxy)")
    else:
        try:
            cck_screenings = scrape_cck(semanas)
            print(f"{len(cck_screenings)} funciones")
        except Exception as e:
            cck_screenings = []
            print(f"error — {e}")

    print("🎬 Scrapeando Museo del Cine...", end=" ", flush=True)
    try:
        museo_screenings = scrape_museo_cine(semanas)
        print(f"{len(museo_screenings)} funciones")
    except Exception as e:
        museo_screenings = []
        print(f"error — {e}")

    print("🎬 Scrapeando Centro Cultural Recoleta...", end=" ", flush=True)
    try:
        ccr_screenings = scrape_ccr()
        print(f"{len(ccr_screenings)} funciones")
    except Exception as e:
        ccr_screenings = []
        print(f"error — {e}")
    from letterboxd import LetterboxdCache, enrich_title

    cache = LetterboxdCache(CACHE_JSON)
    all_screenings = []

    print("🎬 Scrapeando MALBA...", end=" ", flush=True)
    try:
        r = scrape_malba(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Amorina...", end=" ", flush=True)
    try:
        r = scrape_amorina()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Filo Cine (UBA)...", end=" ", flush=True)
    try:
        r = scrape_filo()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Biblioteca Nacional...", end=" ", flush=True)
    try:
        r = scrape_bn()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Centro Cultural de la Cooperación...", end=" ", flush=True)
    try:
        r = scrape_ccd()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Casa del Bicentenario...", end=" ", flush=True)
    try:
        r = scrape_cb()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Biblioteca del Congreso...", end=" ", flush=True)
    try:
        r = scrape_bcn()
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando CEA...", end=" ", flush=True)
    try:
        r = scrape_cea(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Archivo General de la Nación...", end=" ", flush=True)
    try:
        r = scrape_agn(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Bellas Artes...", end=" ", flush=True)
    try:
        r = scrape_bellasartes(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Cinemark + Hoyts (API propia)...", end=" ", flush=True)
    try:
        r = scrape_cinemark_hoyts(semanas)
        all_screenings.extend(r)
        from collections import Counter as _C
        print(", ".join(f"{c}: {n}" for c, n in _C(x.cine for x in r).items()) or "0")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Multiplex...", end=" ", flush=True)
    try:
        r = scrape_multiplex(semanas)
        all_screenings.extend(r)
        from collections import Counter as _C
        print(", ".join(f"{c}: {n}" for c, n in _C(x.cine for x in r).items()) or "0")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Peña sin cadenas (Hasta Trilce)...", end=" ", flush=True)
    try:
        r = scrape_pena_sin_cadenas(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando Arthaus...", end=" ", flush=True)
    try:
        r = scrape_arthaus(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("🎬 Scrapeando CC 25 de Mayo...", end=" ", flush=True)
    try:
        r = scrape_cc25(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    print("📝 Funciones manuales...", end=" ", flush=True)
    try:
        r = scrape_manual(semanas)
        all_screenings.extend(r)
        print(f"{len(r)} funciones")
    except Exception as e:
        print(f"error — {e}")

    async with async_playwright() as pw:
        # Scraping phase — dedicated browser context
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="es-AR")
        page = await ctx.new_page()

        all_screenings.extend(lumiton_screenings)
        all_screenings.extend(cosmos_screenings)
        all_screenings.extend(gaumont_screenings)
        all_screenings.extend(cck_screenings)
        all_screenings.extend(museo_screenings)
        all_screenings.extend(ccr_screenings)

        # Lorca + comerciales: IMDb primero (semana completa), Lanación fallback (solo hoy)
        print("🎬 Scrapeando Lorca + Comerciales (IMDb → Lanación fallback)...")
        try:
            imdb_screenings = await scrape_imdb_then_lanacion(page, semanas)
            all_screenings.extend(imdb_screenings)
            print(f"  ↳ total: {len(imdb_screenings)} funciones")
            # Si Lorca quedó sin nada, último fallback: lorca_manual.json
            if not any(s.cine == "Cine Lorca" for s in imdb_screenings):
                lorca_manual = scrape_lorca()
                if lorca_manual:
                    all_screenings.extend(lorca_manual)
                    print(f"  ↳ fallback manual Lorca: {len(lorca_manual)} funciones")
        except Exception as e:
            print(f"error — {e}")

        salas_playwright = [
            ("Sala Lugones", lambda p: scrape_lugones(p)),
            ("Cacodelphia",  lambda p: scrape_cacodelphia(p)),
        ]
        if sin_proxy:
            print("🎬 Scrapeando Centro Cultural Borges... salteado (--sin-proxy)")
        else:
            salas_playwright.append(
                ("Centro Cultural Borges", lambda p: scrape_borges(p, semanas)))

        for name, fn in salas_playwright:
            print(f"🎬 Scrapeando {name}...", end=" ", flush=True)
            try:
                r = await fn(page)
                all_screenings.extend(r)
                print(f"{len(r)} funciones")
            except Exception as e:
                print(f"error — {e}")

        await browser.close()

        # Enrichment phase — fresh browser context so Letterboxd doesn't see scraping history
        lb_browser = await pw.chromium.launch(headless=True)
        lb_ctx = await lb_browser.new_context(user_agent=UA)
        lb_page = await lb_ctx.new_page()

        # Descartes manuales ANTES del enrichment: las funciones mal scrapeadas
        # (p.ej. un programa doble en un solo título) no tienen match posible en
        # Letterboxd, así que sacarlas acá también ahorra búsquedas inútiles.
        all_screenings, n_desc = descartar_manual(all_screenings)
        if n_desc:
            print(f"  ↳ Descartadas {n_desc} funciones por manual_screenings.json")

        # Para cada título único, juntamos los mejores hints disponibles desde
        # cualquier screening que lo cite (director / año / título original)
        hints: dict[str, dict] = {}
        for s in all_screenings:
            h = hints.setdefault(s.title, {})
            if not h.get("director") and getattr(s, "director", ""):
                h["director"] = s.director
            if not h.get("year") and getattr(s, "year", None):
                h["year"] = s.year
            if not h.get("original") and getattr(s, "original_title", ""):
                h["original"] = s.original_title
            if not h.get("duration") and getattr(s, "duration", None):
                h["duration"] = s.duration

        unique_titles = list(hints.keys())
        print(f"\n🔍 Enriqueciendo {len(unique_titles)} títulos con Letterboxd...")

        title_meta: dict[str, dict] = {}
        for i, title in enumerate(unique_titles, 1):
            sys.stdout.write(f"\r  [{i}/{len(unique_titles)}] {title[:50]:<50}")
            sys.stdout.flush()
            h = hints[title]
            meta = await enrich_title(
                title, lb_page, cache,
                hint_year=h.get("year"),
                hint_director=h.get("director", ""),
                hint_original=h.get("original", ""),
                hint_duration=h.get("duration"),
            )
            title_meta[title] = meta

        print()
        await lb_browser.close()

    # Stopwords del español (palabras que NO se capitalizan en sentence case)
    SPANISH_STOPWORDS = {
        "de", "del", "la", "el", "los", "las", "y", "a", "al", "en",
        "un", "una", "unos", "unas", "por", "con", "para", "sin",
        "lo", "se", "su", "sus", "es", "que", "o", "u", "ni", "mi",
        "ante", "sobre", "tras", "entre", "hacia", "hasta", "desde",
    }

    def _title_case_es(s: str) -> str:
        """'HOMBRE DE LA ATLÁNTIDA' → 'Hombre de la Atlántida'."""
        if not s:
            return s
        out_words: list[str] = []
        for i, w in enumerate(s.split()):
            wl = w.lower()
            if i == 0 or wl not in SPANISH_STOPWORDS:
                # Capitalize preservando acentos (str.capitalize hace lower al resto)
                out_words.append(wl[:1].upper() + wl[1:])
            else:
                out_words.append(wl)
        return " ".join(out_words)

    def _fix_caps(s: str) -> str:
        """Normaliza nombres que vienen TODO EN MAYÚSCULAS (p.ej. directores de
        CEA, donde el innerText hereda un text-transform: uppercase)."""
        return _title_case_es(s) if s and s.isupper() else s

    def _fix_country_caps(s: str) -> str:
        """Como _fix_caps pero preserva las siglas de países (UK, USA, EEUU,
        URSS): sólo title-casea los nombres largos en mayúsculas."""
        if not s:
            return s
        out: list[str] = []
        for part in s.split(","):
            p = part.strip()
            if not p:
                continue
            if p.isupper() and len(p.replace(" ", "")) <= 4:
                out.append(p)            # sigla: se preserva en mayúsculas
            elif p.isupper():
                out.append(_title_case_es(p))
            else:
                out.append(p)
        return ", ".join(out)

    # Unificar países que las distintas fuentes escriben en inglés o español →
    # forma canónica en castellano. La clave se normaliza sin acentos ni
    # puntuación, así "Mexico"/"México"/"méxico" colapsan a una sola entrada.
    _COUNTRY_ALIASES = {
        # Estados Unidos / Reino Unido (siglas y variantes)
        "usa": "Estados Unidos", "us": "Estados Unidos", "eeuu": "Estados Unidos",
        "euu": "Estados Unidos", "unitedstates": "Estados Unidos",
        "unitedstatesofamerica": "Estados Unidos", "estadosunidos": "Estados Unidos",
        "uk": "Reino Unido", "unitedkingdom": "Reino Unido",
        "reinounido": "Reino Unido", "greatbritain": "Reino Unido",
        "granbretana": "Reino Unido", "england": "Reino Unido",
        # Europa
        "france": "Francia", "francia": "Francia",
        "germany": "Alemania", "deutschland": "Alemania", "alemania": "Alemania",
        "spain": "España", "espana": "España",
        "italy": "Italia", "italia": "Italia",
        "belgium": "Bélgica", "belgica": "Bélgica",
        "netherlands": "Países Bajos", "holland": "Países Bajos",
        "paisesbajos": "Países Bajos",
        "portugal": "Portugal",
        "switzerland": "Suiza", "suiza": "Suiza",
        "sweden": "Suecia", "suecia": "Suecia",
        "norway": "Noruega", "noruega": "Noruega",
        "denmark": "Dinamarca", "dinamarca": "Dinamarca",
        "finland": "Finlandia", "finlandia": "Finlandia",
        "poland": "Polonia", "polonia": "Polonia",
        "austria": "Austria",
        "greece": "Grecia", "grecia": "Grecia",
        "ireland": "Irlanda", "irlanda": "Irlanda",
        "russia": "Rusia", "rusia": "Rusia", "ussr": "URSS", "urss": "URSS",
        "hungary": "Hungría", "hungria": "Hungría",
        "romania": "Rumania", "rumania": "Rumania",
        "czechrepublic": "República Checa", "czechia": "República Checa",
        "republicacheca": "República Checa",
        "czechoslovakia": "Checoslovaquia", "checoslovaquia": "Checoslovaquia",
        "turkey": "Turquía", "turquia": "Turquía",
        "iceland": "Islandia", "islandia": "Islandia",
        # América
        "canada": "Canadá",
        "mexico": "México",
        "brazil": "Brasil", "brasil": "Brasil",
        "peru": "Perú",
        "chile": "Chile", "argentina": "Argentina", "uruguay": "Uruguay",
        "paraguay": "Paraguay", "bolivia": "Bolivia", "colombia": "Colombia",
        "venezuela": "Venezuela", "ecuador": "Ecuador", "cuba": "Cuba",
        # Asia / África / Oceanía
        "japan": "Japón", "japon": "Japón",
        "china": "China",
        "southkorea": "Corea del Sur", "korea": "Corea del Sur",
        "republicofkorea": "Corea del Sur", "coreadelsur": "Corea del Sur",
        "northkorea": "Corea del Norte",
        "india": "India",
        "iran": "Irán",
        "israel": "Israel",
        "morocco": "Marruecos", "marruecos": "Marruecos",
        "egypt": "Egipto", "egipto": "Egipto",
        "australia": "Australia",
        "newzealand": "Nueva Zelanda", "nuevazelanda": "Nueva Zelanda",
        "taiwan": "Taiwán", "taiwán": "Taiwán",
        "thailand": "Tailandia", "tailandia": "Tailandia",
        "southafrica": "Sudáfrica", "sudafrica": "Sudáfrica",
    }

    def _country_key(p: str) -> str:
        """Clave de país sin acentos, minúsculas, sólo letras."""
        p = p.lower().translate(str.maketrans("áéíóúü", "aeiouu"))
        return re.sub(r"[^a-z]", "", p)

    def _normalize_country(s: str) -> str:
        """'Usa, Uk' → 'Estados Unidos'; 'France'/'Germany' → 'Francia'/'Alemania'."""
        if not s:
            return s
        seen: list[str] = []
        for part in s.split(","):
            p = part.strip()
            if not p:
                continue
            p = _COUNTRY_ALIASES.get(_country_key(p), p)
            if p not in seen:
                seen.append(p)
        return ", ".join(seen)

    # Construir JSON final
    screenings_out = []
    for s in all_screenings:
        meta = title_meta.get(s.title, {})
        scraped = s.title
        # ¿Cine devolvió todo en MAYÚSCULAS? (Cacodelphia/Arthaus)
        scraped_is_caps = scraped.isupper() if len(scraped) > 3 else False
        tmdb_es = (meta.get("title_es") or "").strip()
        tmdb_en = (meta.get("title_en") or "").strip()

        if not scraped_is_caps:
            # Cine ya nos dio el título con casing decente — respetamos.
            # El cine local SIEMPRE conoce el título local mejor que TMDb.
            display_title = scraped
        elif tmdb_es and tmdb_es.lower() != tmdb_en.lower():
            # Cine en mayúsculas y TMDb tiene una traducción al español
            # genuina (distinta del título en inglés) → usamos TMDb.
            display_title = tmdb_es
        else:
            # Cine en mayúsculas y no hay traducción confiable al español →
            # prettify el scraped a sentence-case en castellano (mantiene
            # nombres propios y stopwords correctos).
            display_title = _title_case_es(scraped)

        screenings_out.append({
            "cine":       s.cine,
            "fecha":      s.fecha,
            "hora":       s.hora,
            "title_es":   display_title,
            "title_en":   tmdb_en or display_title,
            "original_title": (meta.get("original_title") or "").strip(),
            "director":   _fix_caps(getattr(s, "director", "") or meta.get("director") or ""),
            "country":    _normalize_country(_fix_country_caps(getattr(s, "country", "") or meta.get("country") or "")),
            "year":       getattr(s, "year", None) or meta.get("year"),
            "duration":   getattr(s, "duration", None) or meta.get("duration"),
            "genre":      meta.get("genre") or "",
            "letterboxd": meta.get("url") or "",
            "ticket_url": getattr(s, "ticket_url", ""),
            "ciclo":      _fix_caps(getattr(s, "ciclo", "")),
        })

    # Ordenar por fecha + hora
    def sort_key(x):
        from datetime import datetime
        try:
            d = datetime.strptime(x["fecha"], "%Y-%m-%d").date()
        except ValueError:
            from datetime import date
            d = date.max
        try:
            from datetime import datetime as dt
            h = dt.strptime(x["hora"], "%H:%M").time()
        except ValueError:
            from datetime import time
            h = time(23, 59)
        return (d, h)

    screenings_out.sort(key=sort_key)

    # Aplicar overrides manuales de Letterboxd (data/letterboxd_overrides.json)
    # para títulos donde el enrichment automático no logra encontrar la URL.
    if LB_OVERRIDES_JSON.exists():
        try:
            overrides_raw = json.loads(LB_OVERRIDES_JSON.read_text(encoding="utf-8"))
            overrides = {k.lower().strip(): v for k, v in overrides_raw.items()
                         if not k.startswith("_") and v}
            applied = 0
            for s in screenings_out:
                if s.get("letterboxd"):
                    continue
                for cand in (s.get("title_es", ""), s.get("title_en", "")):
                    norm = (cand or "").lower().strip()
                    if norm in overrides:
                        s["letterboxd"] = overrides[norm]
                        applied += 1
                        break
            if applied:
                print(f"  ↳ Letterboxd overrides aplicados a {applied} funciones")
        except Exception as e:
            print(f"  ↳ Overrides omitidos: {e}")

    # Overrides de metadata (data/metadata_overrides.json): corrigen campos que
    # el enrichment matchea mal (p.ej. dos películas con el mismo título).
    # Cada entry matchea por 'title' (case-insensitive) y opcionalmente 'cine',
    # y pisa los campos que estén presentes (director, year, country, genre,
    # duration, letterboxd, title_en, original_title, title_es, ciclo).
    # `ciclo` está en la lista porque hay cines que lo publican y lo dejan de
    # publicar en el medio de un festival: Cacodelphia marcaba sus funciones del
    # DocBuenosAires pegándole "- Doc Bsas" al título y el 19/8/2026 dejó de
    # hacerlo, así que las cuatro que le quedaban se quedaron sin ciclo y no
    # aparecían junto a las del festival.
    # 'title' matchea contra el title_es actual — o sea, contra el título MAL
    # si lo que estás corrigiendo es justamente ese. Una vez corregido el
    # entry deja de matchear, que es lo esperado.
    if METADATA_OVERRIDES_JSON.exists():
        _OVERRIDABLE = ("director", "year", "country", "genre", "duration",
                        "letterboxd", "title_en", "original_title", "title_es",
                        "ciclo")
        try:
            raw = json.loads(METADATA_OVERRIDES_JSON.read_text(encoding="utf-8"))
            entries = raw.get("overrides", []) if isinstance(raw, dict) else raw
            applied = 0
            for s in screenings_out:
                s_title = (s.get("title_es", "") or "").lower().strip()
                for ov in entries:
                    if (ov.get("title", "") or "").lower().strip() != s_title:
                        continue
                    if ov.get("cine") and ov["cine"] != s.get("cine"):
                        continue
                    changed = False
                    for f in _OVERRIDABLE:
                        if f in ov:
                            s[f] = ov[f]
                            changed = True
                    if changed:
                        applied += 1
                    break
            if applied:
                print(f"  ↳ Metadata overrides aplicados a {applied} funciones")
        except Exception as e:
            print(f"  ↳ Metadata overrides omitidos: {e}")

    # Merge con la corrida anterior para no perder funciones que el scrape de hoy
    # no capturó. Tres casos:
    #   1) Comerciales: La Nación sólo expone HOY, así que preservamos sus
    #      funciones FUTURAS ya capturadas en corridas previas.
    #   2) Eventos del CTBA (Lugones, etc.) que en su ÚLTIMO día caen del listado
    #      de "próximos" y dejan de scrapearse → preservamos las funciones de HOY
    #      que estaban antes y ahora faltan (cualquier sala).
    #   3) Los cines que se bajan por el proxy residencial (Borges y CCK):
    #      publican semanas de programación de una vez, pero Cloudflare bloquea
    #      la IP del runner y el proxy se cae por su cuenta (key vencida, sin
    #      créditos). Si la corrida trajo menos funciones que el umbral —señal
    #      de scrape fallido, no de cartelera vacía— preservamos sus funciones
    #      FUTURAS de la corrida anterior. Si el scrape anduvo, la data fresca
    #      manda y no se preserva nada viejo.
    #
    #      El CCK estaba afuera de esta red y por eso desapareció de la web en
    #      dos días: el 22/8/2026 el proxy empezó a contestar 401 y, sin cache,
    #      cada corrida se llevaba puestas las funciones futuras; sólo sobrevivían
    #      las de HOY (caso 2). El Borges, con la misma falla el mismo día, siguió
    #      publicando. Umbral 1 —y no 3 como el Borges— porque el CCK sano puede
    #      tener pocas funciones a la vista (proyecta viernes a domingo): sólo el
    #      cero es inequívocamente una falla.
    COMMERCIAL_PREFIXES = ('Cinemark', 'Hoyts', 'Cinépolis', 'Cinepolis', 'Showcase', 'Multiplex')
    #      Bellas Artes entra en la misma red: el museo y Amigos están los dos
    #      detrás de Cloudflare y el 28/8/2026 el scrape del runner volvió con
    #      CERO funciones (desde casa, 11) — sólo sobrevivieron las de HOY por
    #      el caso 2, así que la sala perdió todo el ciclo de septiembre.
    CINES_CON_CACHE = {'Centro Cultural Borges': 3, 'CCK': 1, 'Bellas Artes': 1}   # cine → mínimo sano
    if CARTELERA_JSON.exists():
        try:
            from datetime import date
            prev_data = json.loads(CARTELERA_JSON.read_text(encoding="utf-8"))
            today_str = date.today().isoformat()

            def _key(s):
                return (s["cine"], s.get("title_es", ""), s.get("fecha", ""), s.get("hora", ""))

            # Cines detrás del proxy cuyo scrape se cayó hoy: los que trajeron
            # menos funciones que su mínimo sano (el Borges sano trae 15-20).
            cache_caidos = {
                cine for cine, minimo in CINES_CON_CACHE.items()
                if sum(1 for s in screenings_out if s.get("cine") == cine) < minimo
            }

            # De dónde saca los links CADA cine en la corrida de hoy. Sirve para
            # no revivir funciones que dejó un scraper que ya no existe: cuando
            # el sitio de un cine se muda (o cambia de ruta), sus funciones
            # viejas apuntan a un host que el scraper de hoy ya no produce.
            # Pasó con Cosmos: el sitio se mudó a cosmos.uba.ar y las 160
            # funciones basura de la corrida anterior —una película con los
            # horarios de todas las demás— volvían por acá, corrida tras
            # corrida, encima de las 32 buenas. Sin este filtro, un día de data
            # mala se vuelve inmortal hasta la medianoche: el scraper arreglado
            # no alcanza para limpiarla.
            def _host(s):
                return urlparse(s.get("ticket_url") or "").netloc.lower()

            hosts_hoy: dict = {}
            for s in screenings_out:
                hosts_hoy.setdefault(s.get("cine", ""), set()).add(_host(s))

            existing_keys = {_key(s) for s in screenings_out}
            restored_comm = restored_today = restored_cache = 0
            descartadas_host = 0
            for s in prev_data.get("screenings", []):
                f = s.get("fecha", "")
                is_comm = any(s.get("cine", "").startswith(p) for p in COMMERCIAL_PREFIXES)
                is_cache = s.get("cine") in cache_caidos
                keep = ((is_comm and f > today_str)
                        or (f == today_str)
                        or (is_cache and f > today_str))
                if not keep or _key(s) in existing_keys:
                    continue
                # El cine trajo funciones hoy pero desde otro origen: la vieja
                # es de un scraper anterior, no una que se cayó del listado.
                hosts = hosts_hoy.get(s.get("cine", ""))
                if hosts and _host(s) not in hosts:
                    descartadas_host += 1
                    continue
                screenings_out.append(s)
                existing_keys.add(_key(s))
                if f == today_str:
                    restored_today += 1
                elif is_cache:
                    restored_cache += 1
                else:
                    restored_comm += 1
            if descartadas_host:
                print(f"  ↳ Merge: {descartadas_host} funciones viejas descartadas "
                      f"(apuntaban a un sitio que su cine ya no usa)")
            if restored_comm or restored_today or restored_cache:
                screenings_out.sort(key=sort_key)
                caidos = ", ".join(sorted(cache_caidos)) or "—"
                print(f"  ↳ Merge: +{restored_comm} comerciales futuras, "
                      f"+{restored_cache} futuras de caché ({caidos}), "
                      f"+{restored_today} funciones de hoy preservadas")
        except Exception as e:
            print(f"  ↳ Merge omitido: {e}")

    # Una misma película no se da dos veces en la misma sala a la misma hora: si
    # aparece repetida es que dos fuentes trajeron la misma función. Pasa cuando
    # una función manual reemplaza a una scrapeada (manual_screenings.json) y el
    # cine después corrige su propio listado: la regla de `descartar` deja de
    # matchear y quedan las dos. Nos quedamos con la primera, que es la manual —
    # scrape_manual corre antes que todos los scrapers.
    vistas: set[tuple] = set()
    unicas = []
    for s in screenings_out:
        k = (s["cine"], s.get("title_es", ""), s.get("fecha", ""), s.get("hora", ""))
        if k in vistas:
            continue
        vistas.add(k)
        unicas.append(s)
    if len(unicas) != len(screenings_out):
        print(f"  ↳ {len(screenings_out) - len(unicas)} funciones duplicadas descartadas")
        screenings_out = unicas

    output = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "screenings": screenings_out,
    }

    CARTELERA_JSON.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ {len(screenings_out)} funciones guardadas en {CARTELERA_JSON}")
    gasto = resumen_proxy()
    if gasto:
        print(f"💳 {gasto}")


def start_server(port: int = 8080) -> None:
    """Levanta un servidor HTTP estático sirviendo todo el directorio del proyecto."""
    os.chdir(HERE)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # silenciar logs

        def end_headers(self):
            # Permitir que el HTML cargue el JSON desde data/
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    with http.server.HTTPServer(("", port), Handler) as httpd:
        print(f"🌐 Servidor corriendo en http://localhost:{port}")
        print(f"   Abrí http://localhost:{port}/web/index.html")
        httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de cines de arte — Buenos Aires")
    parser.add_argument("--serve", action="store_true", help="Levantar servidor web después de scrapear")
    parser.add_argument("--semanas", type=int, default=9, help="Semanas de anticipación (default: 9 ≈ 2 meses)")
    parser.add_argument("--only-serve", action="store_true", help="Solo servidor, sin scrapear")
    parser.add_argument("--sin-proxy", action="store_true",
                        help="Saltear los cines que se bajan por el proxy pago (CCK, Borges)")
    args = parser.parse_args()

    if not args.only_serve:
        asyncio.run(run_scraper(semanas=args.semanas, sin_proxy=args.sin_proxy))

    if args.serve or args.only_serve:
        start_server()
