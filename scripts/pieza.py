#!/usr/bin/env python3
"""
Arma piezas de Instagram con texto (stories y posts) a partir de una ficha
JSON, siempre con las mismas medidas, tipos y colores: los de marca/marca.css.
Las reglas están en marca/MANUAL.md.

    python3 scripts/pieza.py marca/ejemplos/sala-nueva.json
    python3 scripts/pieza.py ficha.json --formato feed     # pisa el formato
    python3 scripts/pieza.py ficha.json --solo-html        # no saca PNG

Salida: posts/piezas/<nombre de la ficha>/<formato>/slide-N.png

La ficha:
    {
      "formato": "story" | "feed" | ["story", "feed"],
      "fecha":   "2026-11-19",          # día en que se publica: define el acento
      "rotulo":  "sala nueva",          # cabecera, va en mayúsculas
      "bajada":  "club lucero",         # cabecera, va en el color del día
      "pie":     "cines de buenos aires",
      "festival": "rojo-sangre",        # slug de data/festivales.json: la centrada usa su logo
      "slides": [
        {"tipo": "centrada", "mini": "...", "antetitulo": "...", "titular": "...", "lineas": ["...", "..."]},
        {"tipo": "frase", "texto": "...", "nota": "..."},
        {"tipo": "texto", "titular": "...", "parrafos": ["...", "..."], "nota": "..."},
        {"tipo": "lista", "items": [
            {"clave": "20:00", "etiqueta": "MALBA", "sala": "malba",
             "titulo": "...", "secundario": "...", "nota": "..."}]}
      ]
    }

*así* dentro de un texto lo pinta del color del día (una vez por slide, no más).
El script corta con error si el texto usa un signo prohibido o si no entra en
el lienzo: no achica la letra ni aprieta los márgenes para que entre.
"""
import argparse
import asyncio
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MARCA = RAIZ / "marca"

# Mismo orden y mismos valores que DAY_ACCENT de instagram.html (domingo = 0).
ACENTO_DIA = ["#b86b52", "#5f7fa6", "#b79a58", "#8b74a8", "#5f9b7f", "#b06d86", "#5f9c96"]

# Lo que no sale nunca. El punto medio y las rayas largas delatan texto de IA;
# las banderas y los emojis no son de la marca.
PROHIBIDOS = {
    "·": "punto medio", "•": "viñeta", "∙": "punto medio",
    "・": "punto medio", "‧": "punto medio", "⋅": "punto medio",
    "—": "raya larga", "–": "raya corta", "―": "raya larga",
}
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF☀-➿️]")

LIMITES = {"rotulo": 20, "bajada": 26, "pie": 34, "etiqueta": 24, "clave": 5, "mini": 34}


class FichaMala(Exception):
    pass


def revisar(texto: str, donde: str) -> None:
    for ch, nombre in PROHIBIDOS.items():
        if ch in texto:
            raise FichaMala(f"{donde}: tiene {nombre} ({ch!r}). Usá coma, punto o salto de línea.")
    if EMOJI.search(texto):
        raise FichaMala(f"{donde}: tiene un emoji o una bandera.")
    if "!!" in texto or "…" in texto:
        raise FichaMala(f"{donde}: sin signos repetidos ni puntos suspensivos de un solo carácter.")


def t(texto, donde: str, limite: str = "") -> str:
    """Texto de la ficha a HTML: revisa, escapa y convierte *así* en acento."""
    if not isinstance(texto, str) or not texto.strip():
        raise FichaMala(f"{donde}: falta el texto.")
    texto = texto.strip()
    revisar(texto, donde)
    if limite and len(texto) > LIMITES[limite]:
        raise FichaMala(f"{donde}: {len(texto)} caracteres, el máximo es {LIMITES[limite]}.")
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html.escape(texto))


def logo_festival(slug: str) -> Path:
    """El logo que la web ya usa para ese festival (data/festivales.json)."""
    fests = json.loads((RAIZ / "data" / "festivales.json").read_text(encoding="utf-8"))["festivales"]
    f = next((x for x in fests if x.get("slug") == slug), None)
    if f is None:
        raise FichaMala(f"festival {slug!r}: no está en data/festivales.json. "
                        f"Slugs: {', '.join(x['slug'] for x in fests)}")
    if not f.get("logo") or not (RAIZ / f["logo"]).exists():
        raise FichaMala(f"festival {slug!r}: no tiene logo en la web. Cargalo ahí primero.")
    return RAIZ / f["logo"]


def cuerpo_slide(s: dict, i: int, festival: str = "") -> str:
    d = f"slide {i}"
    tipo = s.get("tipo")
    nota = f'<p class="nota">{t(s["nota"], d + " nota")}</p>' if s.get("nota") else ""
    if tipo == "frase":
        return f'<div class="cuerpo"><p class="frase">{t(s.get("texto"), d)}</p>{nota}</div>'
    if tipo == "texto":
        partes = []
        if s.get("titular"):
            partes.append(f'<p class="titular">{t(s["titular"], d + " titular")}</p>')
        for p in s.get("parrafos", []):
            partes.append(f'<p class="parrafo">{t(p, d + " párrafo")}</p>')
        if not partes:
            raise FichaMala(f"{d}: un slide de texto lleva titular, párrafos o los dos.")
        return f'<div class="cuerpo">{"".join(partes)}{nota}</div>'
    if tipo == "lista":
        items = s.get("items") or []
        if not items:
            raise FichaMala(f"{d}: la lista está vacía.")
        con_clave = [bool(it.get("clave")) for it in items]
        if any(con_clave) and not all(con_clave):
            raise FichaMala(f"{d}: o todas las filas llevan clave o ninguna.")
        filas = []
        for n, it in enumerate(items, 1):
            dd = f"{d} fila {n}"
            clases = ["fila"]
            clave = ""
            if it.get("clave"):
                clave = f'<div class="clave">{t(it["clave"], dd + " clave", "clave")}</div>'
            else:
                clases.append("sin-clave")
            etq = ""
            if it.get("etiqueta"):
                sala = re.sub(r"[^a-z0-9]", "", it.get("sala", ""))
                cls = f"etiqueta cine-{sala}" if sala else "etiqueta"
                etq = f'<span class="{cls}">{t(it["etiqueta"], dd + " etiqueta", "etiqueta")}</span>'
            else:
                clases.append("sin-etiqueta")
            sec = f'<div class="secundario">{t(it["secundario"], dd)}</div>' if it.get("secundario") else ""
            nt = f'<div class="nota">{t(it["nota"], dd)}</div>' if it.get("nota") else ""
            filas.append(
                f'<div class="{" ".join(clases)}">{clave}<div class="fila-cuerpo">{etq}'
                f'<div class="fila-titulo">{t(it.get("titulo"), dd + " título")}</div>{sec}{nt}</div></div>'
            )
        return f'<div class="cuerpo lista">{"".join(filas)}</div>'
    if tipo == "centrada":
        ante = f'<p class="ante">{t(s["antetitulo"], d + " antetítulo")}</p>' if s.get("antetitulo") else ""
        lineas = s.get("lineas") or []
        if len(lineas) > 3:
            raise FichaMala(f"{d}: debajo del logo van tres líneas como máximo.")
        abajo = "".join(
            f'<p class="{"dato" if n == 0 else "dato2"}">{t(l, d + " línea")}</p>' for n, l in enumerate(lineas))
        fest = s.get("festival") or festival
        logo = logo_festival(fest) if fest else RAIZ / "logo.png"
        return (f'<div class="cuerpo centro{" con-fest" if fest else ""}"><div class="arriba">{ante}'
                f'<p class="nombre">{t(s.get("titular"), d + " titular")}</p></div>'
                f'<img class="logo{" fest" if fest else ""}" src="{logo.as_uri()}" alt="">'
                f'<div class="abajo">{abajo}</div></div>')
    raise FichaMala(f"{d}: tipo {tipo!r} no existe. Hay cuatro: centrada, frase, texto, lista.")


def armar_html(ficha: dict, formato: str) -> str:
    if formato not in ("story", "feed"):
        raise FichaMala(f"formato {formato!r}: sólo story (1080x1920) o feed (1080x1350).")
    dia = date.fromisoformat(ficha.get("fecha") or date.today().isoformat())
    acento = ACENTO_DIA[(dia.weekday() + 1) % 7]
    slides = ficha.get("slides") or []
    if not slides:
        raise FichaMala("la ficha no tiene slides.")
    if formato == "feed" and len(slides) > 10:
        raise FichaMala("un carrusel lleva 10 slides como máximo.")
    con_cab = any(s.get("tipo") != "centrada" for s in slides)
    cab = ""
    if con_cab:
        cab = (f'<div class="cab"><div class="rotulo">{t(ficha.get("rotulo"), "rótulo", "rotulo")}</div>'
               f'<div class="bajada">{t(ficha.get("bajada"), "bajada", "bajada")}</div></div>')
    pie_txt = t(ficha.get("pie", "cines de buenos aires"), "pie", "pie")
    total = len(slides)
    piezas = []
    for i, s in enumerate(slides, 1):
        num = f'<span class="num">{i} / {total}</span> ' if total > 1 else ""
        if s.get("tipo") == "centrada":
            mini = s.get("mini") or ficha.get("mini") or ""
            mini = t(mini, f"slide {i} mini título", "mini") if mini else ""
            piezas.append(
                f'<div class="pieza {formato} centrada" id="slide-{i}"><div class="mini">{mini}</div>'
                f'{cuerpo_slide(s, i, ficha.get("festival", ""))}'
                f'<div class="firma">{num}sitedigo.com</div></div>')
            continue
        piezas.append(
            f'<div class="pieza {formato}" id="slide-{i}">{cab}{cuerpo_slide(s, i)}'
            f'<div class="pie"><span>{pie_txt}</span><span>{num}<span class="url">sitedigo.com</span></span></div></div>'
        )
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">'
        f'<link rel="stylesheet" href="{(MARCA / "marca.css").as_uri()}">'
        f"<style>:root{{--accent:{acento}}} body{{display:flex;flex-direction:column;gap:40px}}</style>"
        f'</head><body>{"".join(piezas)}</body></html>'
    )


async def sacar_png(html_path: Path, out_dir: Path, total: int) -> list:
    from playwright.async_api import async_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    for viejo in out_dir.glob("slide-*.png"):
        viejo.unlink()
    guardados = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=2)
        page = await ctx.new_page()
        await page.goto(html_path.as_uri(), wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        desbordes = await page.evaluate("""
            [...document.querySelectorAll('.pieza')].map((p, i) => {
              const c = p.querySelector('.cuerpo');
              const alto = c.scrollHeight - c.clientHeight;
              const ancho = [...p.querySelectorAll('.rotulo,.bajada,.pie,.etiqueta,.clave')]
                .some(e => e.scrollWidth > e.clientWidth + 1);
              const cab2 = [...p.querySelectorAll('.rotulo,.bajada,.mini')]
                .some(e => e.getBoundingClientRect().height > parseFloat(getComputedStyle(e).fontSize) * 1.3);
              return {i: i + 1, alto, ancho, cab2};
            }).filter(d => d.alto > 1 || d.ancho || d.cab2)
        """)
        if desbordes:
            await browser.close()
            msgs = []
            for d in desbordes:
                if d["alto"] > 1:
                    msgs.append(f"slide {d['i']}: sobran {d['alto']} px de texto. Acortalo o partilo en dos slides.")
                if d["cab2"] or d["ancho"]:
                    msgs.append(f"slide {d['i']}: el rótulo, la bajada o el mini título no entran en una línea.")
            raise FichaMala("\n".join(msgs))
        for i in range(1, total + 1):
            el = await page.query_selector(f"#slide-{i}")
            out = out_dir / f"slide-{i}.png"
            await el.screenshot(path=str(out), type="png")
            guardados.append(out)
        await browser.close()
    return guardados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ficha")
    ap.add_argument("--formato", choices=["story", "feed"])
    ap.add_argument("--solo-html", action="store_true")
    args = ap.parse_args()

    ficha_path = Path(args.ficha).resolve()
    ficha = json.loads(ficha_path.read_text(encoding="utf-8"))
    formatos = [args.formato] if args.formato else ficha.get("formato", "story")
    if isinstance(formatos, str):
        formatos = [formatos]
    base = RAIZ / "posts" / "piezas" / ficha_path.stem
    try:
        for fmt in formatos:
            doc = armar_html(ficha, fmt)
            out_dir = base / fmt
            out_dir.mkdir(parents=True, exist_ok=True)
            html_path = out_dir / "pieza.html"
            html_path.write_text(doc, encoding="utf-8")
            if args.solo_html:
                print(f"  {html_path.relative_to(RAIZ)}")
                continue
            for p in asyncio.run(sacar_png(html_path, out_dir, len(ficha["slides"]))):
                print(f"  {p.relative_to(RAIZ)}")
    except FichaMala as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
