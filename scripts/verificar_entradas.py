#!/usr/bin/env python3
"""
Verifica los links de entradas de las funciones cargadas a mano.

    python3 scripts/verificar_entradas.py --ciclo FICUBA
    python3 scripts/verificar_entradas.py --ciclo FICUBA \\
        --listado "https://www.ficuba.com/es/programacion"

Por qué existe: los festivales que se cargan a mano desde una guía en PDF
(FIC.UBA 2026) llevan como link la ficha de cada película en el sitio del
festival, y esa URL se arma con el título ("Primavera temprana" →
/es/pelicula/primavera-temprana). Armarla es adivinar cómo el sitio
escribe el título: un signo o un apóstrofo distinto y el link abre una página
vacía o la home. Acá se abre cada una y sólo se da por buena si la página
nombra la película (título o director).

Para las que no abren, prueba variantes del slug y, si se le pasa `--listado`,
recorre el listado del festival (con su paginación) juntando los links de
película, y sugiere el que mejor coincide. Al final imprime los reemplazos.

Necesita red hacia el sitio del festival. Si el entorno no la tiene, corre en
CI con el workflow verificar-entradas.yml (workflow_dispatch).
"""
import argparse
import html
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "data" / "manual_screenings.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def norm(t: str) -> str:
    t = re.sub(r"['’‘`´]", "", t or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


def slug(t: str, apostrofo: str = "") -> str:
    t = re.sub(r"['’‘`´]", apostrofo, t or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def bajar(url: str) -> tuple[int, str, str]:
    """(status, url final, texto de la página)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            cuerpo = r.read().decode("utf-8", errors="replace")
            return r.status, r.geturl(), cuerpo
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except Exception as e:                      # red, TLS, timeout
        return 0, url, str(e)


def texto(cuerpo: str) -> str:
    sin_tags = re.sub(r"(?s)<(script|style).*?</\1>|<[^>]+>", " ", cuerpo)
    return norm(html.unescape(sin_tags))


def es_la_pelicula(cuerpo: str, titulo: str, directores: str) -> bool:
    """La página es la ficha de la película: el título en un encabezado, o el
    apellido de alguno de sus directores en una página que no sea un listado.

    Una ficha inexistente suele volver 200 igual (la plantilla vacía, la home o
    el listado), así que el status solo no alcanza. Y un listado nombra todas
    las películas: por eso el título tiene que estar en un encabezado y el
    director no vale si la página linkea a muchas fichas."""
    encabezados = " ".join(re.findall(r"(?is)<h[1-4][^>]*>(.*?)</h[1-4]>", cuerpo))
    if norm(titulo) and f" {norm(titulo)} " in f" {texto(encabezados)} ":
        return True
    if len(re.findall(r'href="[^"]*/pelicula/', cuerpo)) > 10:
        return False
    t = f" {texto(cuerpo)} "
    for d in re.split(r",|\sy\s", directores or ""):
        apellido = norm(d).split(" ")[-1:]
        if apellido and len(apellido[0]) > 3 and f" {apellido[0]} " in t:
            return True
    return False


def links_del_listado(listado: str, prefijo: str, max_paginas: int = 30) -> dict[str, str]:
    """{slug: url} de todas las películas del listado, siguiendo su paginación
    (links a la misma ruta con otra query)."""
    base = urllib.parse.urlparse(listado)
    pendientes, vistas, pelis = [listado], set(), {}
    while pendientes and len(vistas) < max_paginas:
        url = pendientes.pop(0)
        if url in vistas:
            continue
        vistas.add(url)
        status, _, cuerpo = bajar(url)
        if status != 200:
            print(f"   (listado {url}: HTTP {status})")
            continue
        for href in re.findall(r'href="([^"]+)"', cuerpo):
            u = urllib.parse.urljoin(url, html.unescape(href))
            p = urllib.parse.urlparse(u)
            if p.path.startswith(prefijo):
                pelis[p.path[len(prefijo):].strip("/")] = f"{p.scheme}://{p.netloc}{p.path}"
            elif p.netloc == base.netloc and p.path == base.path and p.query and u not in vistas:
                pendientes.append(u)
    return pelis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ciclo", required=True,
                    help='festival: se verifican las funciones con ciclo "X" o "X - …"')
    ap.add_argument("--listado", help="listado de películas del festival, para sugerir links")
    args = ap.parse_args()

    data = json.loads(MANUAL.read_text(encoding="utf-8"))
    pelis: dict[str, dict] = {}
    for m in data.get("screenings", []):
        c = m.get("ciclo", "")
        if not (c == args.ciclo or c.startswith(args.ciclo + " - ")) or not m.get("ticket_url"):
            continue
        pelis.setdefault(m["ticket_url"], {
            "title": m["title"], "original": m.get("original_title", ""),
            "directores": m.get("_directores") or m.get("director", ""),
        })

    print(f"Verificando {len(pelis)} link(s)…\n")
    malos: dict[str, dict] = {}
    for url, p in pelis.items():
        status, final, cuerpo = bajar(url)
        if status == 200 and final == url and es_la_pelicula(cuerpo, p["title"], p["directores"]):
            print(f"✅ {url}")
            continue
        print(f"❌ {url}  (HTTP {status}{', otra página' if status == 200 else ''}"
              f"{', redirige a ' + final if final != url else ''}) — {p['title']}")
        malos[url] = p

    listado = {}
    if malos and args.listado:
        prefijo = urllib.parse.urlparse(next(iter(malos))).path.rsplit("/", 1)[0] + "/"
        listado = links_del_listado(args.listado, prefijo)
        print(f"\nEl listado tiene {len(listado)} película(s).")

    reemplazos, sin_arreglo = {}, []
    for url, p in malos.items():
        base = url.rsplit("/", 1)[0]
        candidatos = [f"{base}/{s}" for s in dict.fromkeys(
            s for s in (slug(p["title"], "-"), slug(p["title"]), slug(p["original"]),
                        slug(re.sub(r"\(.*?\)", "", p["title"])))
            if s and f"{base}/{s}" != url)]
        # Del listado: el slug que contiene todas las palabras del título, o al revés.
        t = set(norm(p["title"]).split())
        candidatos += [u for s, u in listado.items()
                       if u not in candidatos and u != url
                       and (t <= set(s.split("-")) or set(s.split("-")) <= t)]
        for c in candidatos:
            status, final, cuerpo = bajar(c)
            if status == 200 and final == c and es_la_pelicula(cuerpo, p["title"], p["directores"]):
                reemplazos[url] = c
                break
        else:
            sin_arreglo.append((url, p["title"]))

    print("\n" + "=" * 72)
    print(f"OK: {len(pelis) - len(malos)} · ARREGLADOS: {len(reemplazos)} · "
          f"SIN ARREGLO: {len(sin_arreglo)}")
    if reemplazos:
        print("\nReemplazar en data/manual_screenings.json:\n")
        print(json.dumps(reemplazos, ensure_ascii=False, indent=2))
    if sin_arreglo:
        print("\nSin arreglo — mirar a mano:")
        for url, titulo in sin_arreglo:
            print(f"  · {titulo}: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
