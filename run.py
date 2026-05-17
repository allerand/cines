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

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def run_scraper(semanas: int = 2) -> None:
    from scraper import (
        scrape_malba, scrape_lugones, scrape_cacodelphia,
        scrape_lorca, scrape_lorca_imdb, scrape_lumiton_agenda, scrape_cosmos,
        scrape_gaumont, scrape_cck, scrape_arthaus,
    )
    # Lorca: el scraping vía IMDb necesita playwright y se hace abajo.
    lorca_screenings: list = []

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

    async with async_playwright() as pw:
        # Scraping phase — dedicated browser context
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="es-AR")
        page = await ctx.new_page()

        all_screenings.extend(lumiton_screenings)
        all_screenings.extend(cosmos_screenings)
        all_screenings.extend(gaumont_screenings)
        all_screenings.extend(cck_screenings)

        # Cine Lorca: scraping vía IMDb usa playwright en este contexto
        print("🎬 Scrapeando Cine Lorca (IMDb)...", end=" ", flush=True)
        try:
            lorca_screenings = await scrape_lorca_imdb(page, semanas)
            print(f"{len(lorca_screenings)} funciones")
            if not lorca_screenings:
                # Fallback al JSON manual si IMDb no devolvió nada
                lorca_screenings = scrape_lorca()
                if lorca_screenings:
                    print(f"  ↳ fallback manual: {len(lorca_screenings)} funciones")
            all_screenings.extend(lorca_screenings)
        except Exception as e:
            print(f"error — {e}")
            lorca_screenings = scrape_lorca()
            if lorca_screenings:
                all_screenings.extend(lorca_screenings)

        for name, fn in [
            ("Sala Lugones", lambda p: scrape_lugones(p)),
            ("Cacodelphia",  lambda p: scrape_cacodelphia(p)),
            ("Arthaus",      lambda p: scrape_arthaus(p, semanas)),

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

    # Construir JSON final
    screenings_out = []
    for s in all_screenings:
        meta = title_meta.get(s.title, {})
        # Prefer the cinema's own scraped metadata over Letterboxd; fall back to LB.
        screenings_out.append({
            "cine":       s.cine,
            "fecha":      s.fecha,
            "hora":       s.hora,
            "title_es":   s.title,
            "title_en":   meta.get("title_en") or s.title,
            "director":   getattr(s, "director", "") or meta.get("director") or "",
            "country":    getattr(s, "country", "") or meta.get("country") or "",
            "year":       getattr(s, "year", None) or meta.get("year"),
            "duration":   getattr(s, "duration", None) or meta.get("duration"),
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
    parser.add_argument("--semanas", type=int, default=2, help="Semanas de anticipación (default: 2)")
    parser.add_argument("--only-serve", action="store_true", help="Solo servidor, sin scrapear")
    args = parser.parse_args()

    if not args.only_serve:
        asyncio.run(run_scraper(semanas=args.semanas))

    if args.serve or args.only_serve:
        start_server()
