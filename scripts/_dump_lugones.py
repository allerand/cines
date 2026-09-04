#!/usr/bin/env python3
"""TEMPORAL — valida la memoria de eventos del CTBA contra el sitio real.

Siembra el archivo con la Integral Pere Portabella (que ya NO está en el
listado) y corre scrape_lugones: si la memoria sirve, el ciclo se relee de su
/ver/. Como sus funciones ya pasaron, el evento tiene que quedar olvidado
después. Se borra junto con el parche a probe-acceso.yml.
"""
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scraper                                                # noqa: E402
from playwright.async_api import async_playwright             # noqa: E402

PORTABELLA = "https://complejoteatral.gob.ar/ver/Integral-Pere-Portabella"


async def correr(rotulo):
    print(f"\n{rotulo}\n" + "=" * 70)
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(user_agent=scraper.UA, locale="es-AR")
        page = await ctx.new_page()
        try:
            return await scraper.scrape_lugones(page)
        finally:
            await b.close()


async def main() -> int:
    hoy = date.today()
    scraper.CTBA_EVENTOS_PATH.write_text(json.dumps({
        PORTABELLA: {"titulo": "Integral Pere Portabella",
                     "ticket_url": "https://entradasba.buenosaires.gob.ar/evento/9ee70625",
                     "visto": (hoy - timedelta(days=3)).isoformat()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"memoria sembrada con Portabella (visto hace 3 días); hoy es {hoy}")

    funciones = await correr("Corrida con el ciclo caído del listado")
    print(f"\n{len(funciones)} funciones en total")
    portabella = [f for f in funciones
                  if "portabella" in (f.ciclo or "").lower()
                  or f.title.lower() in ("tren de sombras", "los golfos",
                                         "el silencio antes de bach")]
    print(f"del ciclo Portabella: {len(portabella)}")
    for f in portabella:
        print(f"    {f.fecha} {f.hora} {f.title}")

    guardado = json.loads(scraper.CTBA_EVENTOS_PATH.read_text(encoding="utf-8"))
    print(f"\nmemoria después de la corrida: {len(guardado)} evento(s)")
    for u, e in guardado.items():
        print(f"  {e.get('titulo','?')[:44]:<44} visto={e.get('visto')}")
    print(f"\n¿Portabella quedó olvidado? "
          f"{'sí — su ciclo ya no da funciones' if PORTABELLA not in guardado else 'NO, sigue guardado'}")

    # Y los eventos del listado de hoy tienen que haber quedado anotados.
    print(f"\nLugones hoy: {sum(1 for f in funciones if f.fecha == hoy.isoformat())} funciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
