#!/usr/bin/env python3
"""TEMPORAL — ¿por qué el Lugones perdió el ciclo Portabella?

Mira las tres capas: qué eventos de cine lista hoy el CTBA, qué dice la ficha
del evento que desapareció, y qué devuelve el scraper. Se borra junto con el
parche a probe-acceso.yml.
"""
import asyncio
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup                                    # noqa: E402
from playwright.async_api import async_playwright                # noqa: E402
from scraper import (UA, fetch_ctba_ver_page_sync,               # noqa: E402
                     scrape_lugones)

LISTADO = "https://complejoteatral.gob.ar/sala-leopoldo-lugones"
# El evento que se cayó: "Integral Pere Portabella", con funciones el 2 y el 3.
EVENTO = "https://entradasba.buenosaires.gob.ar/evento/9ee70625-4d4a-455b-8874-323c88d5b59b"


async def main() -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=UA, locale="es-AR")
        page = await ctx.new_page()

        await page.goto(LISTADO, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        soup = BeautifulSoup(await page.content(), "html.parser")

        tarjetas = soup.select("div.list-item-programacion")
        print(f"El listado del Lugones trae {len(tarjetas)} tarjetas\n" + "=" * 70)
        for card in tarjetas:
            cat = card.select_one("span.category")
            h2 = card.select_one("h2.mango-grotesque")
            ver = card.select_one("a[href*='/ver/']")
            buy = card.select_one("a.button.buy")
            print(f"  [{(cat.get_text(strip=True) if cat else '?'):<12}] "
                  f"{(h2.get_text(strip=True) if h2 else '?')[:60]}")
            print(f"      ver={ver['href'][:88] if ver and ver.get('href') else '—'}")
            print(f"      buy={buy['href'][:88] if buy and buy.get('href') else '—'}")

        print("\n\n¿Portabella sigue en el listado?\n" + "=" * 70)
        txt = soup.get_text(" ", strip=True).lower()
        for pista in ("portabella", "tren de sombras", "los golfos", "silencio antes de bach"):
            print(f"  {pista:26} → {'SÍ' if pista in txt else 'no'} aparece en la página")

        print("\n\nLa ficha del evento en entradasba\n" + "=" * 70)
        try:
            resp = await page.goto(EVENTO, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(3000)
            print(f"  status {resp.status if resp else '?'}")
            cuerpo = BeautifulSoup(await page.content(), "html.parser").get_text(" ", strip=True)
            print(f"  {len(cuerpo)} caracteres de texto")
            print("  " + cuerpo[:1200])
        except Exception as e:
            print(f"  no abre: {type(e).__name__}: {e}")

        await browser.close()

    print("\n\nLa página /ver/ del ciclo (la que parsea el scraper)\n" + "=" * 70)
    for ver in ["https://complejoteatral.gob.ar/ver/integral-pere-portabella",
                "https://complejoteatral.gob.ar/ver/Integral Pere Portabella"]:
        t = fetch_ctba_ver_page_sync(ver)
        print(f"  {ver[:70]} → {len(t) if t else 'None'}")
        if t:
            print("   ", t[:400].replace("\n", " | "))
            break

    print("\n\nLo que devuelve scrape_lugones hoy\n" + "=" * 70)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=UA, locale="es-AR")
        page = await ctx.new_page()
        try:
            funciones = await scrape_lugones(page)
        finally:
            await browser.close()
    hoy = date.today().isoformat()
    print(f"\n{len(funciones)} funciones; {sum(1 for f in funciones if f.fecha == hoy)} son de hoy ({hoy})")
    for f in sorted(funciones, key=lambda x: (x.fecha, x.hora))[:14]:
        marca = "  <-- HOY" if f.fecha == hoy else ""
        print(f"  {f.fecha} {f.hora}  {f.title[:42]:<42} | {f.ciclo[:32]}{marca}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
