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
import sys
import threading
from datetime import datetime
from pathlib import Path

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


async def run_scraper(semanas: int = 9) -> None:
    from scraper import (
        scrape_malba, scrape_lugones, scrape_cacodelphia,
        scrape_lorca, scrape_lumiton_agenda, scrape_cosmos,
        scrape_gaumont, scrape_cck, scrape_arthaus, scrape_museo_cine,
        scrape_ccr, scrape_imdb_then_lanacion, scrape_amorina, scrape_cea,
        scrape_filo, scrape_bn, scrape_cc25, scrape_ccd, scrape_cb,
        scrape_borges,
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

        for name, fn in [
            ("Sala Lugones", lambda p: scrape_lugones(p)),
            ("Cacodelphia",  lambda p: scrape_cacodelphia(p)),
            ("Arthaus",      lambda p: scrape_arthaus(p, semanas)),
            ("CEA",          lambda p: scrape_cea(p)),
            ("CC 25 de Mayo", lambda p: scrape_cc25(p, semanas)),
            ("Centro Cultural Borges", lambda p: scrape_borges(p, semanas)),
        ]:
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
            "director":   _fix_caps(getattr(s, "director", "") or meta.get("director") or ""),
            "country":    _fix_caps(getattr(s, "country", "") or meta.get("country") or ""),
            "year":       getattr(s, "year", None) or meta.get("year"),
            "duration":   getattr(s, "duration", None) or meta.get("duration"),
            "genre":      meta.get("genre") or "",
            "letterboxd": meta.get("url") or "",
            "ticket_url": getattr(s, "ticket_url", ""),
            "ciclo":      getattr(s, "ciclo", ""),
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
    # duration, letterboxd, title_en, original_title).
    if METADATA_OVERRIDES_JSON.exists():
        _OVERRIDABLE = ("director", "year", "country", "genre", "duration",
                        "letterboxd", "title_en", "original_title")
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
    # no capturó. Dos casos:
    #   1) Comerciales: La Nación sólo expone HOY, así que preservamos sus
    #      funciones FUTURAS ya capturadas en corridas previas.
    #   2) Eventos del CTBA (Lugones, etc.) que en su ÚLTIMO día caen del listado
    #      de "próximos" y dejan de scrapearse → preservamos las funciones de HOY
    #      que estaban antes y ahora faltan (cualquier sala).
    COMMERCIAL_PREFIXES = ('Cinemark', 'Hoyts', 'Cinépolis', 'Cinepolis', 'Showcase', 'Multiplex')
    if CARTELERA_JSON.exists():
        try:
            prev_data = json.loads(CARTELERA_JSON.read_text(encoding="utf-8"))
            today_str = date.today().isoformat()

            def _key(s):
                return (s["cine"], s.get("title_es", ""), s.get("fecha", ""), s.get("hora", ""))

            existing_keys = {_key(s) for s in screenings_out}
            restored_comm = restored_today = 0
            for s in prev_data.get("screenings", []):
                f = s.get("fecha", "")
                is_comm = any(s.get("cine", "").startswith(p) for p in COMMERCIAL_PREFIXES)
                keep = (is_comm and f > today_str) or (f == today_str)
                if not keep or _key(s) in existing_keys:
                    continue
                screenings_out.append(s)
                existing_keys.add(_key(s))
                if f == today_str:
                    restored_today += 1
                else:
                    restored_comm += 1
            if restored_comm or restored_today:
                screenings_out.sort(key=sort_key)
                print(f"  ↳ Merge: +{restored_comm} comerciales futuras, "
                      f"+{restored_today} funciones de hoy preservadas")
        except Exception as e:
            print(f"  ↳ Merge omitido: {e}")

    output = {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "screenings": screenings_out,
    }

    CARTELERA_JSON.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ {len(screenings_out)} funciones guardadas en {CARTELERA_JSON}")


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
    args = parser.parse_args()

    if not args.only_serve:
        asyncio.run(run_scraper(semanas=args.semanas))

    if args.serve or args.only_serve:
        start_server()
