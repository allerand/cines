#!/usr/bin/env python3
"""TEMPORAL — vuelca el listado de portal.salalucida.org y un resumen de cada
evento. Se borra junto con el parche a probe-acceso.yml."""
import re
import sys
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://portal.salalucida.org"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="replace")


def compactar(html):
    out = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    out = re.sub(r"<svg\b.*?</svg>", "<svg/>", out, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", "", out, flags=re.S | re.I)
    out = re.sub(r"<script\b.*?</script>", "", out, flags=re.S | re.I)
    return re.sub(r"\s+", " ", out)


def main():
    html = get(BASE + "/")
    soup = BeautifulSoup(html, "html.parser")
    main_tag = soup.find("main")
    print(f"===== LISTADO <main> ({len(html)} bytes la página) =====")
    print(compactar(str(main_tag))[:26000])

    enlaces = []
    for a in soup.find_all("a", href=re.compile(r"/eventos/")):
        u = a["href"]
        u = u if u.startswith("http") else BASE + u
        if u not in enlaces:
            enlaces.append(u)
    print(f"\n\n===== {len(enlaces)} eventos =====")

    for u in enlaces:
        try:
            s = BeautifulSoup(get(u), "html.parser")
        except Exception as e:
            print(f"\n-- {u}: {e}")
            continue
        art = s.select_one("main article")
        estado = art.get("data-estado") if art else "?"
        h2 = art.find("h2") if art else None
        fecha = art.select_one(".fecha h4") if art else None
        print(f"\n-- {u}")
        print(f"   estado={estado!r} h2={h2.get_text(' ', strip=True) if h2 else None!r} "
              f"fecha={fecha.get_text(' ', strip=True) if fecha else None!r}")
        desc = s.select_one(".e-evento.descripcion")
        if not desc:
            print("   (sin bloque descripcion)")
            continue
        for nodo in desc.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li"]):
            t = nodo.get_text(" ", strip=True).replace("\xa0", " ").strip()
            if not t:
                continue
            print(f"   {nodo.name}: {t[:180]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
