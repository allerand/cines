#!/usr/bin/env python3
"""TEMPORAL — vuelca el HTML de portal.salalucida.org desde el runner.

No es parte del proyecto: se borra apenas el scraper de Sala Lúcida esté
escrito contra el HTML de verdad.
"""
import re
import sys
import asyncio
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}
BASE = "https://portal.salalucida.org"
TOPE = 60000


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


async def get_browser(url):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(user_agent=UA, locale="es-AR")
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2500)
            return (resp.status if resp else 0), await page.content()
        finally:
            await b.close()


def compactar(html):
    """Saca lo que no aporta al parser y colapsa espacios."""
    out = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    out = re.sub(r"<svg\b.*?</svg>", "<svg/>", out, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", "", out, flags=re.S | re.I)
    # los <script> se van salvo los ld+json, que suelen traer todo servido
    def _script(m):
        return m.group(0) if "ld+json" in m.group(0)[:120].lower() else ""
    out = re.sub(r"<script\b.*?</script>", _script, out, flags=re.S | re.I)
    out = re.sub(r"\s+", " ", out)
    return out


def volcar(rotulo, url, html, status):
    c = compactar(html)
    print(f"\n\n===== {rotulo} · {url} · status {status} · "
          f"{len(html)} bytes crudos · {len(c)} compactado =====")
    print(c[:TOPE])
    if len(c) > TOPE:
        print(f"…[cortado en {TOPE}]")


async def main():
    urls_api = set()
    paginas = []

    status, html = get(BASE + "/")
    print(f"listado urllib: status {status}, {len(html)} bytes")
    if status != 200 or "eventos/" not in html:
        print("→ urllib no alcanzó, voy con Chromium")
        status, html = await get_browser(BASE + "/")
        print(f"listado chromium: status {status}, {len(html)} bytes")
    paginas.append(("LISTADO", BASE + "/", html, status))

    urls_api |= set(re.findall(r"[\"'](/api/[^\"'\s]{2,120})[\"']", html))

    enlaces = []
    for href in re.findall(r'href="([^"]*/eventos/[^"]*)"', html):
        u = href if href.startswith("http") else BASE + href
        if u not in enlaces:
            enlaces.append(u)
    print(f"\nlinks a /eventos/ encontrados: {len(enlaces)}")
    for u in enlaces:
        print("  ", u)

    objetivo = [BASE + "/eventos/tierra-citrus-e207"]
    for u in enlaces:
        if u not in objetivo and len(objetivo) < 4:
            objetivo.append(u)

    for u in objetivo:
        st, h = get(u)
        if st != 200 or len(h) < 3000:
            st, h = await get_browser(u)
        urls_api |= set(re.findall(r"[\"'](/api/[^\"'\s]{2,120})[\"']", h))
        paginas.append(("EVENTO", u, h, st))

    for rotulo, u, h, st in paginas:
        volcar(rotulo, u, h, st)

    print("\n\n===== posibles endpoints de API =====")
    for u in sorted(urls_api):
        print("  ", u)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
