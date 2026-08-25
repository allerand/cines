#!/usr/bin/env python3
"""
¿Por qué no podemos entrar a este sitio, y con qué sí?

    python3 scripts/probe_acceso.py            # los sitios que están bloqueando
    python3 scripts/probe_acceso.py --url URL  # uno suelto

Existe porque "HTTP 403" no dice qué hacer. Un 403 puede ser la IP (y entonces
hace falta salir por otro lado), puede ser el fingerprint del cliente (y
entonces alcanza con pedirlo desde un navegador de verdad) o puede ser el
challenge de Cloudflare (que necesita ejecutar JS). Son tres arreglos
distintos y desde el log del scraper no se distinguen.

Prueba la misma URL con clientes cada vez más parecidos a un navegador y dice
cuál es el primero que entra. El scraper después usa ese.

Contexto: el 21/8/2026, entre las 05:00 y las 20:30 ART, palaciolibertad.gob.ar
y la API del Borges pasaron de contestarle normal al runner de GitHub a darle
403 — las dos el mismo día. casadelbicentenario.cultura.gob.ar ya venía así.
"""
import argparse
import asyncio
import json
import re
import sys
import urllib.error
import urllib.request

UA_NAV = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Las tres puertas que se cerraron, más una de control que sabemos que abre.
OBJETIVOS = [
    ("CCK · listado",        "https://palaciolibertad.gob.ar/cine/"),
    ("Borges · API listado", "https://centroculturalborges.gob.ar/api/public/"
                             "eventos-destacados?disciplina=cine"),
    ("Bicentenario · listado", "https://casadelbicentenario.cultura.gob.ar/actividades/"),
    ("CONTROL (Gaumont)",    "https://www.cinegaumont.ar/Default"),
]

_CF = re.compile(r"Just a moment|challenge-platform|cf-browser-verification|"
                 r"__cf_chl|Enable JavaScript and cookies", re.IGNORECASE)


def _veredicto(cuerpo: str) -> str:
    if _CF.search(cuerpo[:4000]):
        return "challenge de Cloudflare (200 pero sin contenido)"
    return f"OK · {len(cuerpo)} bytes"


def intento_urllib(url: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return _veredicto(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def prueba_1_urllib_simple(url: str) -> str:
    """Lo que hace hoy el scraper: urllib con un User-Agent y nada más."""
    return intento_urllib(url, {"User-Agent": UA_NAV})


def prueba_2_urllib_headers(url: str) -> str:
    """urllib con el juego de headers completo de un navegador. Si esto alcanza,
    el bloqueo miraba headers faltantes y no hace falta navegador."""
    return intento_urllib(url, {
        "User-Agent": UA_NAV,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    })


async def prueba_3_playwright(url: str) -> str:
    """Chromium de verdad. Cambia el fingerprint de TLS y de HTTP/2, manda los
    headers en el orden que manda un navegador y ejecuta el JS del challenge.
    Es la prueba que decide si se puede arreglar sin pagar un proxy."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "playwright no instalado"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--disable-blink-features=AutomationControlled"])
            ctx = await browser.new_context(
                user_agent=UA_NAV, locale="es-AR",
                viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = resp.status if resp else 0
                # El challenge tarda unos segundos en resolverse solo.
                await page.wait_for_timeout(4000)
                cuerpo = await page.content()
                if status >= 400 and not _CF.search(cuerpo[:4000]):
                    return f"HTTP {status}"
                v = _veredicto(cuerpo)
                return f"{v} (status {status})"
            finally:
                await browser.close()
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:120]}"


async def sondear(nombre: str, url: str) -> None:
    print(f"\n── {nombre}\n   {url}")
    print(f"   1. urllib + UA .......... {prueba_1_urllib_simple(url)}")
    print(f"   2. urllib + headers ..... {prueba_2_urllib_headers(url)}")
    print(f"   3. Chromium (playwright)  {await prueba_3_playwright(url)}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", help="sondear esta URL (repetible)")
    args = ap.parse_args()

    objetivos = [(u, u) for u in args.url] if args.url else OBJETIVOS
    print("Sondeo de acceso — qué cliente entra y cuál no")
    for nombre, url in objetivos:
        await sondear(nombre, url)
    print("\nLectura: si 1 falla y 3 entra, el bloqueo es por fingerprint de "
          "cliente y se arregla bajando la página con Chromium — sin proxy "
          "pago. Si 3 también da 403, el bloqueo es por IP y no hay forma "
          "desde el runner: hace falta salir por otra red.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
