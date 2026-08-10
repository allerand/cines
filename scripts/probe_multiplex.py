#!/usr/bin/env python3
"""
Sonda de reconocimiento para multiplex.com.ar.

No scrapea nada: mira el HTML que sirve el server y reporta DÓNDE están los
horarios y con qué atributos vienen etiquetados. Con ese reporte se escriben
selectores reales en vez de adivinados.

Por qué existe: DevTools mostró que elegir una fecha en multiplex.com.ar no
dispara ningún request de datos. Eso significa que TODA la grilla (fechas ×
complejos × funciones) ya viene en el HTML inicial y el filtro es client-side.
Un filtro client-side necesita leer los datos de algún lado: atributos data-*,
un <script> con JSON, o JSON-LD. Esta sonda busca los tres.

Uso:
    python scripts/probe_multiplex.py
    python scripts/probe_multiplex.py https://multiplex.com.ar/peliculas/insaciable/

Guarda los HTML crudos en /tmp/multiplex_probe/ por si hace falta mirarlos a
mano, e imprime un reporte acotado (pensado para copiar y pegar entero).
"""

import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

OUT_DIR = Path("/tmp/multiplex_probe")

# Páginas por defecto: la home (grilla por complejo + carrusel de fechas) y una
# ficha de película (el bloque "Ver Horarios y Comprar Entradas").
DEFAULT_URLS = [
    "https://multiplex.com.ar/",
    "https://multiplex.com.ar/peliculas/yo-narciso/",
]

HORA_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")
FECHA_ISO_RE = re.compile(r"\b20\d{2}-[01]\d-[0-3]\d\b")
# Claves que delatan un blob de funciones embebido en un <script>
CLAVES_JS = ("funcion", "funciones", "horario", "showtime", "showtimes",
             "sesion", "session", "complejo", "cartelera", "sala")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def corta(s, n=90):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[:n] + "…"


def firma(tag) -> str:
    """<div class="a b" data-fecha="2026-08-13"> → div.a.b[data-fecha=2026-08-13]"""
    partes = [tag.name]
    clases = tag.get("class") or []
    if clases:
        partes.append("." + ".".join(clases[:3]))
    datos = [f"{k}={corta(v, 28)}" for k, v in tag.attrs.items()
             if k.startswith("data-") or k in ("id", "value", "datetime")]
    if datos:
        partes.append("[" + " ".join(datos[:5]) + "]")
    return "".join(partes)


def seccion(titulo):
    print(f"\n{'=' * 70}\n{titulo}\n{'=' * 70}")


def probe(url: str) -> None:
    seccion(f"URL: {url}")
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  ✗ no se pudo bajar: {e}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nombre = (re.sub(r"[^a-z0-9]+", "_", url.lower().split("//", 1)[-1]).strip("_")
              or "index") + ".html"
    (OUT_DIR / nombre).write_text(html, encoding="utf-8")
    print(f"  HTML crudo: {OUT_DIR / nombre}  ({len(html):,} bytes)")

    # ── 1. La pregunta decisiva: ¿los horarios están en el HTML del server? ──
    horas_crudas = HORA_RE.findall(html)
    print(f"\n[1] Horarios HH:MM en el HTML crudo: {len(horas_crudas)} matches")
    if not horas_crudas:
        print("    ⚠️  NINGUNO → la grilla se arma por JS después de cargar.")
        print("        En ese caso hay que ir por playwright (load_page) y no por urllib.")
    fechas_iso = sorted(set(FECHA_ISO_RE.findall(html)))
    print(f"    Fechas ISO (YYYY-MM-DD) presentes: {len(fechas_iso)} distintas"
          + (f" → {fechas_iso[:12]}" if fechas_iso else ""))

    soup = BeautifulSoup(html, "html.parser")

    # ── 2. JSON-LD (Yoast está instalado; puede traer Event/ScreeningEvent) ──
    seccion_ld = soup.find_all("script", type="application/ld+json")
    print(f"\n[2] Bloques JSON-LD: {len(seccion_ld)}")
    for sc in seccion_ld[:4]:
        try:
            data = json.loads(sc.string or "{}")
        except Exception:
            print("    (no parsea como JSON)")
            continue
        nodos = data.get("@graph", data if isinstance(data, list) else [data])
        for n in nodos[:8]:
            if isinstance(n, dict):
                print(f"    @type={n.get('@type')}  keys={list(n.keys())[:10]}")

    # ── 3. Todos los atributos data-* del documento ─────────────────────────
    #     Un filtro client-side de fecha/complejo TIENE que leer de acá.
    conteo = Counter()
    muestras = defaultdict(list)
    for tag in soup.find_all(True):
        for k, v in tag.attrs.items():
            if not k.startswith("data-"):
                continue
            conteo[k] += 1
            val = corta(v, 40)
            if val and val not in muestras[k] and len(muestras[k]) < 3:
                muestras[k].append(val)
    print(f"\n[3] Atributos data-* distintos: {len(conteo)}")
    interesantes = ("fecha", "date", "day", "dia", "complejo", "cinema", "cine",
                    "hora", "time", "sala", "idioma", "lang", "film", "movie",
                    "pelicula", "id", "filter", "tab", "target")
    for k, n in conteo.most_common(60):
        marca = "★" if any(p in k for p in interesantes) else " "
        print(f"  {marca} {k:<34} ×{n:<5} {muestras[k]}")

    # ── 4. El ancestro de cada horario: acá salen fecha/complejo/sala ────────
    print("\n[4] Cadena de ancestros de los primeros horarios visibles")
    vistos = 0
    for tag in soup.find_all(string=HORA_RE):
        padre = tag.parent
        if padre is None or padre.name in ("script", "style"):
            continue
        texto = corta(tag, 40)
        if not HORA_RE.fullmatch(texto.strip()) and len(texto) > 24:
            continue          # párrafos que casualmente mencionan una hora
        cadena = []
        cur = padre
        for _ in range(6):
            if cur is None or cur.name in ("body", "[document]"):
                break
            cadena.append(firma(cur))
            cur = cur.parent
        print(f"  · '{texto}'")
        for i, c in enumerate(reversed(cadena)):
            print(f"      {'  ' * i}└ {c}")
        vistos += 1
        if vistos >= 6:
            break
    if not vistos:
        print("    (ningún horario suelto en el DOM)")

    # ── 5. Selects del formulario: dan el mapeo id → complejo/sala/idioma ────
    print("\n[5] <select> del formulario de horarios")
    for sel in soup.find_all("select")[:8]:
        print(f"  · {firma(sel)}  name={sel.get('name')}")
        for op in sel.find_all("option")[:12]:
            print(f"      value={op.get('value')!r:<28} {corta(op.get_text(), 44)}")

    # ── 6. Datepicker: qué días vienen habilitados y cómo se marcan ──────────
    print("\n[6] Elementos que parecen días del calendario")
    # Sin cortocircuito: interesa ver los días habilitados Y los deshabilitados,
    # que es lo que dice qué fechas tienen función.
    cand, ids = [], set()
    for grupo in (soup.find_all(attrs={"data-date": True}),
                  soup.find_all(attrs={"data-fecha": True}),
                  soup.select("[class*=day], [class*=dia], [class*=date], [class*=fecha]")):
        for c in grupo:
            if id(c) not in ids:
                ids.add(id(c))
                cand.append(c)
    for c in cand[:20]:
        clases = " ".join(c.get("class") or [])
        deshab = "DISABLED" if ("disabled" in clases.lower()
                                or c.has_attr("disabled")) else ""
        print(f"  · {firma(c)}  txt={corta(c.get_text(), 24)!r} {deshab}")

    # ── 7. <script> inline con pinta de traer las funciones ─────────────────
    print("\n[7] <script> inline con datos de funciones")
    for sc in soup.find_all("script"):
        if sc.get("src"):
            continue
        cuerpo = sc.string or ""
        if len(cuerpo) < 120:
            continue
        bajo = cuerpo.lower()
        hits = [k for k in CLAVES_JS if k in bajo]
        if not hits or not HORA_RE.search(cuerpo):
            continue
        var = re.search(r"(?:var|let|const)\s+(\w+)\s*=", cuerpo)
        print(f"  · {len(cuerpo):,} bytes  var={var.group(1) if var else '?'}  "
              f"claves={hits}")
        pos = HORA_RE.search(cuerpo).start()
        print(f"    …{corta(cuerpo[max(0, pos - 220):pos + 220], 460)}…")


def probe_lanacion() -> None:
    """Atajo: si La Nación ya publica Multiplex, no hace falta parsear nada.

    Los siete comerciales actuales salen de ahí con 4 valores de config
    (scraper.py: LANACION_COMMERCIAL_CINEMAS). Si Multiplex está en la lista,
    agregarlo es una línea por sucursal.
    """
    seccion("EXTRA: ¿La Nación ya lista Multiplex?")
    for url in ("https://www.lanacion.com.ar/cartelera-de-cine/",
                "https://www.lanacion.com.ar/cartelera-de-cine/salas/"):
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  {url} → {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        encontrados = set()
        for a in soup.find_all("a", href=re.compile(r"/cartelera-de-cine/sala/")):
            href = a["href"]
            if "multiplex" in href.lower() or "multiplex" in a.get_text().lower():
                encontrados.add((href, corta(a.get_text(), 40)))
        print(f"  {url} → {len(encontrados)} links con 'multiplex'")
        for href, txt in sorted(encontrados):
            print(f"      {href}   {txt}")


if __name__ == "__main__":
    urls = sys.argv[1:] or DEFAULT_URLS
    for u in urls:
        probe(u)
    if len(sys.argv) == 1:
        probe_lanacion()
    print("\n\nListo. Pegame la salida entera (o los HTML de /tmp/multiplex_probe/).")
