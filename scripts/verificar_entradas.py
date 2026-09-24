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
import time
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


PAUSA = 1.0


def bajar(url: str) -> tuple[int, str, str]:
    """(status, url final, texto de la página).

    Con una pausa antes de cada pedido: la segunda corrida seguida contra
    ficuba.com (unos 250 pedidos en diez minutos) volvió con 403 en todo."""
    time.sleep(PAUSA)
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


def fichas_linkeadas(cuerpo: str, url: str) -> int:
    """A cuántas OTRAS películas linkea la página."""
    propia = urllib.parse.urlparse(url).path.rstrip("/")
    otras = {urllib.parse.urlparse(h).path.rstrip("/")
             for h in re.findall(r'href="([^"]*/pelicula/[^"#?]+)', cuerpo)}
    return len(otras - {propia})


def es_la_pelicula(cuerpo: str, titulo: str, directores: str, url: str = "") -> bool:
    """La página es la ficha de la película: no es un listado, y nombra la
    película (el título en un encabezado, o el apellido de un director).

    Una ficha inexistente vuelve 200 igual, y en ficuba.com lo que vuelve es el
    listado de la programación, que nombra a todas las películas de su página
    con su título en un encabezado. La primera versión miraba el título antes
    que el listado y aprobó cortometrajes-de-alice-guy, que no abre: por eso
    el listado se descarta primero, con cualquier señal."""
    if fichas_linkeadas(cuerpo, url) > 3:
        return False
    encabezados = " ".join(re.findall(r"(?is)<h[1-4][^>]*>(.*?)</h[1-4]>", cuerpo))
    if norm(titulo) and f" {norm(titulo)} " in f" {texto(encabezados)} ":
        return True
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
    ap.add_argument("--listado", action="append", default=[],
                    help="página que linkea películas del festival (repetible), para sugerir links")
    ap.add_argument("--solo", action="append", default=[],
                    help="verificar sólo los títulos que contengan esto (repetible)")
    args = ap.parse_args()

    data = json.loads(MANUAL.read_text(encoding="utf-8"))
    pelis: dict[str, dict] = {}
    rutas: list[str] = []          # dónde viven las fichas, de todos los links del festival
    for m in data.get("screenings", []):
        c = m.get("ciclo", "")
        if not (c == args.ciclo or c.startswith(args.ciclo + " - ")) or not m.get("ticket_url"):
            continue
        rutas.append(urllib.parse.urlparse(m["ticket_url"]).path.rsplit("/", 1)[0] + "/")
        if args.solo and not any(norm(x) in norm(m["title"]) for x in args.solo):
            continue
        pelis.setdefault((m["ticket_url"], m["title"]), {
            "title": m["title"], "original": m.get("original_title", ""),
            "directores": m.get("_directores") or m.get("director", ""),
        })

    print(f"Verificando {len(pelis)} link(s)…\n")
    malos: dict[str, dict] = {}
    rechazos = 0
    # Por (link, título): varias pueden compartir el link genérico a la
    # programación, y cada una necesita su propia ficha.
    for (url, titulo), p in pelis.items():
        status, final, cuerpo = bajar(url)
        # Si el sitio nos está bloqueando, seguir sólo alarga el bloqueo.
        rechazos = rechazos + 1 if status in (403, 429) else 0
        if rechazos >= 5:
            print(f"\n⛔ {rechazos} rechazos seguidos (HTTP {status}): el sitio está bloqueando "
                  f"al runner. Corta acá; probar más tarde.")
            return 1
        if status == 200 and final == url and es_la_pelicula(cuerpo, p["title"], p["directores"], url):
            print(f"✅ {url}")
            continue
        otras = fichas_linkeadas(cuerpo, url) if status == 200 else 0
        print(f"❌ {url}  (HTTP {status}"
              f"{f', otra página: linkea a {otras} películas' if status == 200 else ''}"
              f"{', redirige a ' + final if final != url else ''}) — {p['title']}")
        malos[(url, titulo)] = p

    # Donde viven la mayoría de los links del festival: el que falló puede
    # apuntar a la programación general, y su ruta no sirve de prefijo.
    prefijo = max(set(rutas), key=rutas.count) if rutas else "/"
    listado = {}
    if malos and args.listado:
        for l in args.listado:
            listado.update(links_del_listado(l, prefijo))
        print(f"\nLos listados tienen {len(listado)} película(s).")

    reemplazos, sin_arreglo = {}, []
    for (url, titulo), p in malos.items():
        u = urllib.parse.urlparse(url)
        base = f"{u.scheme}://{u.netloc}{prefijo.rstrip('/')}"
        candidatos = [f"{base}/{s}" for s in dict.fromkeys(
            s for s in (slug(p["title"], "-"), slug(p["title"]), slug(p["original"]),
                        slug(re.sub(r"\(.*?\)", "", p["title"])))
            if s and f"{base}/{s}" != url)]
        # Del listado: el slug que tiene el título adentro, pegado (así
        # "c-est-pas-moi" y "cest-pas-moi" son lo mismo), o al revés.
        pegados = [norm(x).replace(" ", "") for x in (p["title"], p["original"]) if norm(x)]
        candidatos += [u for s, u in listado.items()
                       if u not in candidatos and u != url
                       and any(t in s.replace("-", "") or s.replace("-", "") in t for t in pegados)]
        for c in candidatos:
            status, final, cuerpo = bajar(c)
            if status == 200 and final == c and es_la_pelicula(cuerpo, p["title"], p["directores"], c):
                reemplazos[titulo] = c
                break
        else:
            sin_arreglo.append((url, titulo))

    if listado:
        # Lo que el listado tiene y no usa ninguna función: ahí suele estar el
        # link bueno de las que no se pudieron arreglar solas.
        usados = {u for u, _ in pelis} | set(reemplazos.values())
        sobran = sorted(s for s, u in listado.items() if u not in usados)
        if sobran:
            print(f"\nEn el listado y sin usar ({len(sobran)}): {', '.join(sobran)}")

    print("\n" + "=" * 72)
    print(f"OK: {len(pelis) - len(malos)} · ARREGLADOS: {len(reemplazos)} · "
          f"SIN ARREGLO: {len(sin_arreglo)}")
    if reemplazos:
        print("\nLink bueno por título (reemplazar en data/manual_screenings.json):\n")
        print(json.dumps(reemplazos, ensure_ascii=False, indent=2))
    if sin_arreglo:
        print("\nSin arreglo — mirar a mano:")
        for url, titulo in sin_arreglo:
            print(f"  · {titulo}: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
