#!/usr/bin/env python3
"""
El monitor de festivales.

Un festival se carga una vez (a mano, película por película, o lo trae el
scraper de alguna sala) y después nadie lo mira: si el festival cambia la
grilla, si quedó sin funciones, si una sala lo escribe con otro nombre o si el
próximo ya anunció fechas, la web no se entera. Esto lo mira todas las semanas.

Tres frentes:

  1. El registro (data/festivales.json): de cada festival, si está por
     empezar, en curso o terminado; cuántas funciones tiene la web (contadas
     como las cuenta index.html) y en qué salas; si hay funciones fuera de sus
     fechas, programas sin lista de películas, o funciones que lo nombran sin
     usar su nombre del registro (y entonces no aparecen en su búsqueda).
  2. La web de cada festival: se guarda una huella del texto de la página
     (data/festivales_web.json) y se avisa cuando cambia, con las líneas
     nuevas. No interpreta la grilla: dice "cambió, mirala".
  3. El radar (data/festivales_radar.json): los festivales que vuelven todos
     los años. Si se acerca su mes y el registro no tiene la edición de este
     año, avisa para ir a buscarla. Las fechas confirmadas van en `proxima`,
     que es lo que completa el agente monitor-festivales.

Sólo stdlib. La parte 2 necesita red; con `leer=None` se saltea.
"""
from __future__ import annotations

import calendar
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from categorias import ERROR, AVISO, ciclo_base, norm      # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Con cuánta anticipación se mira un festival.
DIAS_URGENTE = 7          # sin funciones a esta distancia es para hoy
DIAS_AVISO = 30           # sin funciones a esta distancia es para ir mirando
DIAS_WEB = 45             # desde cuándo se vigila su web
DIAS_RADAR = 45           # cuánto antes de su mes habitual entra al radar
DIAS_MEMORIA = 45         # una edición terminada hace menos que esto sigue "cubierta"
DIAS_YA_FUE = 240         # un festival anual no vuelve antes de ocho meses

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]
_MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
# Una línea que habla de la grilla: trae una hora o un día.
_DE_GRILLA = re.compile(
    r"\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s?hs?\b|\b\d{1,2}/\d{1,2}\b|"
    r"\b\d{1,2}\s+de\s+(?:" + "|".join(_MESES) + r")\b|"
    r"\b(?:lun|mar|mi[eé]|jue|vie|s[áa]b|dom)\w*\s+\d{1,2}\b", re.IGNORECASE)


class Nota(NamedTuple):
    sev: str
    slug: str        # el festival (para el id del hallazgo)
    nombre: str
    regla: str
    msg: str
    efimera: bool = False    # no se anuncia como "resuelta" cuando deja de salir
    corto: str = ""          # para la sección Festivales: "19 al 29 nov, empieza en 3 días"


def _n(n: int, uno: str, muchos: str) -> str:
    """"1 función" / "3 funciones": el número con su sustantivo."""
    return f"{n} {uno if n == 1 else muchos}"


def _fecha(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s or "")
    except ValueError:
        return None


def dia_mes(d: date) -> str:
    return f"{d.day}/{d.month}"


def rango_texto(desde: Optional[date], hasta: Optional[date]) -> str:
    """"17 al 22 nov", "22 oct al 1 nov", como lo escribe la web."""
    if not desde:
        return ""
    if not hasta or hasta == desde:
        return f"{desde.day} {_MESES_CORTO[desde.month - 1]}"
    if desde.month == hasta.month:
        return f"{desde.day} al {hasta.day} {_MESES_CORTO[hasta.month - 1]}"
    return (f"{desde.day} {_MESES_CORTO[desde.month - 1]} al "
            f"{hasta.day} {_MESES_CORTO[hasta.month - 1]}")


def cuando_texto(estado: str, desde: Optional[date], hasta: Optional[date], hoy: date) -> str:
    if estado == "en-curso":
        if hasta:
            quedan = (hasta - hoy).days
            return "termina hoy" if quedan == 0 else f"en curso, quedan {quedan} día{'s' if quedan != 1 else ''}"
        return "en curso"
    if estado == "proximo" and desde:
        faltan = (desde - hoy).days
        return "empieza mañana" if faltan == 1 else f"empieza en {faltan} días"
    if estado == "terminado" and hasta:
        return f"terminó el {dia_mes(hasta)}"
    return ""


# ---------------------------------------------------------------------------
# El registro
# ---------------------------------------------------------------------------

def _coincide(s: dict, q: str) -> bool:
    """La misma cuenta que hace el buscador de index.html (coincideBusqueda):
    así el número de acá es el que aparece al tocar el festival."""
    return q in " ".join(str(s.get(k) or "") for k in
                         ("title_es", "title_en", "original_title", "director", "ciclo")).lower()


def _claves(f: dict) -> list:
    """El nombre del ciclo del registro y sus alias, normalizados."""
    out = []
    for x in [f.get("ciclo")] + list(f.get("alias") or []):
        k = norm(x or "")
        if k and k not in out:
            out.append(k)
    return out


def _nombra(texto: str, claves: list) -> bool:
    n = f" {norm(texto)} "
    return any(f" {k} " in n for k in claves)


def ficha(f: dict, filas: list, hoy: date, root: Optional[Path] = None) -> dict:
    """El estado de un festival del registro. `filas`: las funciones de Buenos
    Aires de hoy en adelante."""
    archivo_ok = True
    if f.get("archivo"):
        funciones = []
        try:
            p = (root or Path(".")) / f["archivo"]
            funciones = [s for s in json.loads(p.read_text(encoding="utf-8")).get("screenings", [])
                         if s.get("fecha", "") >= hoy.isoformat()]
        except Exception:
            archivo_ok = False
    else:
        q = (f.get("ciclo") or "").strip().lower()
        funciones = [s for s in filas if _coincide(s, q)] if q else []

    fechas = sorted(s.get("fecha", "") for s in funciones if s.get("fecha"))
    desde = _fecha(f.get("desde") or "") or _fecha(fechas[0] if fechas else "")
    hasta = _fecha(f.get("hasta") or "") or _fecha(fechas[-1] if fechas else "")
    if hasta and hasta < hoy:
        estado = "terminado"
    elif desde and desde <= hoy:
        estado = "en-curso"
    elif desde:
        estado = "proximo"
    else:
        estado = "sin-fecha"         # ni fechas ni funciones: la web no lo muestra
    sin_ficha = [s for s in funciones if not s.get("director") and not s.get("letterboxd")]
    return {
        "slug": f.get("slug", ""), "nombre": f.get("nombre", ""), "estado": estado,
        "desde": desde, "hasta": hasta, "con_fechas": bool(f.get("desde")),
        "funciones": funciones, "n": len(funciones),
        "salas": sorted({s.get("cine", "") for s in funciones}),
        "sin_ficha": sin_ficha, "lugar": f.get("lugar", ""), "archivo": f.get("archivo", ""),
        "archivo_ok": archivo_ok, "web": f.get("web", ""), "logo": f.get("logo", ""),
        "registro": f,
    }


def revisar_registro(registro: list, filas: list, hoy: date, manual: Optional[dict] = None,
                     root: Optional[Path] = None) -> tuple[list, list]:
    """(fichas, notas) de los festivales del registro."""
    fichas = [ficha(f, filas, hoy, root) for f in registro]
    notas: list[Nota] = []

    def nota(sev, fi, regla, msg, **kw):
        notas.append(Nota(sev, fi["slug"], fi["nombre"], regla, msg, **kw))

    for fi in fichas:
        f, estado = fi["registro"], fi["estado"]
        vivo = estado in ("en-curso", "proximo")
        faltan = (fi["desde"] - hoy).days if fi["desde"] else None

        # Sin funciones cuando ya debería tenerlas.
        if vivo and not fi["n"]:
            if f.get("archivo") and not fi["archivo_ok"]:
                nota(ERROR, fi, "sin-archivo",
                     f"no se puede leer su archivo ({f['archivo']}): la página del festival sale vacía")
            elif estado == "en-curso":
                nota(ERROR, fi, "sin-funciones",
                     f"está en curso (hasta el {dia_mes(fi['hasta'])}) y no tiene ninguna "
                     f"función en la web" if fi["hasta"] else
                     "está en curso y no tiene ninguna función en la web")
            elif faltan is not None and faltan <= DIAS_URGENTE:
                nota(ERROR, fi, "sin-funciones",
                     f"empieza el {dia_mes(fi['desde'])} (en {faltan} día{'s' if faltan != 1 else ''}) "
                     f"y todavía no tiene funciones cargadas")
            elif faltan is not None and faltan <= DIAS_AVISO:
                nota(AVISO, fi, "sin-funciones",
                     f"empieza el {dia_mes(fi['desde'])} y no tiene funciones: mirar si ya publicó la grilla")

        # Funciones fuera de las fechas que dice el registro.
        if fi["n"] and fi["con_fechas"] and f.get("hasta"):
            fuera = [s for s in fi["funciones"]
                     if not (f["desde"] <= s.get("fecha", "") <= f["hasta"])]
            if fuera:
                ej = fuera[0]
                nota(AVISO, fi, "fuera-de-fechas",
                     f"{_n(len(fuera), 'función', 'funciones')} fuera de sus fechas ({rango_texto(fi['desde'], fi['hasta'])}): "
                     f"{ej.get('cine')}, {ej.get('fecha')}, «{ej.get('title_es')}». O el registro "
                     f"tiene mal las fechas o la función no es del festival")

        # Programas sin lista de películas: una fila por sesión, sin ficha.
        if vivo and fi["sin_ficha"]:
            titulos = []
            for s in fi["sin_ficha"]:
                if s.get("title_es") not in titulos:
                    titulos.append(s.get("title_es"))
            muestra = ", ".join(f"«{t}»" for t in titulos[:4]) + ("…" if len(titulos) > 4 else "")
            nota(AVISO, fi, "sin-lista",
                 f"{_n(len(titulos), 'programa', 'programas')} sin lista de películas ({muestra}): mirar si el "
                 f"festival ya la publicó para cargarlas una por una")

        # Funciones que lo nombran con otro nombre: no aparecen en su búsqueda.
        if not f.get("archivo") and f.get("ciclo"):
            claves = _claves(f)
            propias = {id(s) for s in fi["funciones"]}
            perdidas = [s for s in filas if id(s) not in propias
                        and _nombra(ciclo_base(s.get("ciclo") or ""), claves)]
            if perdidas:
                ej = perdidas[0]
                nota(ERROR, fi, "otro-nombre",
                     f"{_n(len(perdidas), 'función lo nombra', 'funciones lo nombran')} en el ciclo sin usar su nombre del "
                     f"registro («{f['ciclo']}»), y no aparecen al tocar el festival: "
                     f"{ej.get('cine')}, ciclo «{ej.get('ciclo')}»")

        # La entrada del registro, completa.
        if vivo:
            faltantes = [que for campo, que in (("logo", "el logo"), ("web", "la web"),
                                                ("bajada", "la bajada")) if not f.get(campo)]
            if not f.get("desde") or not f.get("hasta"):
                faltantes.append("las fechas")
            if faltantes:
                nota(AVISO, fi, "registro-incompleto",
                     "en el registro le falta " + _enumerar(faltantes))

    # Festivales con grilla a mano que no están en el registro: no aparecen en
    # la pestaña Festivales (pasó con FIC.UBA: su ciclo no dice "festival").
    conocidos = [k for f in registro for k in _claves(f)]
    for regla in (manual or {}).get("festivales", []):
        if (regla.get("hasta") or "") < hoy.isoformat():
            continue
        if not _nombra(regla.get("ciclo", ""), conocidos):
            notas.append(Nota(AVISO, "manual-" + norm(regla.get("ciclo", "")).replace(" ", "-"),
                              regla.get("ciclo", ""), "sin-registro",
                              "tiene la grilla cargada a mano (manual_screenings.json) y no está "
                              "en data/festivales.json: no aparece en la pestaña Festivales"))
    return fichas, notas


def sueltos(registro: list, filas: list) -> list:
    """Ciclos que dicen "festival" y no son de ninguno del registro. La web
    los lista igual en la pestaña Festivales, con el nombre del ciclo tal cual
    lo escribe la sala: [(ciclo, funciones, salas)]."""
    conocidos = [k for f in registro if not f.get("archivo") for k in _claves(f)]
    vistos: dict = {}
    for s in filas:
        ciclo = s.get("ciclo") or ""
        if not re.search(r"\bfestival\b", ciclo, re.IGNORECASE) or _nombra(ciclo, conocidos):
            continue
        base = ciclo_base(ciclo)
        n, salas = vistos.get(base, (0, set()))
        vistos[base] = (n + 1, salas | {s.get("cine", "")})
    return sorted(((c, n, sorted(sl)) for c, (n, sl) in vistos.items()), key=lambda x: -x[1])


def _enumerar(cosas: list) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


# ---------------------------------------------------------------------------
# El radar
# ---------------------------------------------------------------------------

def _en_ventana(meses: list, hoy: date) -> Optional[int]:
    """El mes habitual que está cerca (desde DIAS_RADAR antes de que empiece
    hasta que termina), o None."""
    for anio in (hoy.year, hoy.year + 1):
        for m in meses or []:
            if not 1 <= m <= 12:
                continue
            inicio = date(anio, m, 1)
            fin = date(anio, m, calendar.monthrange(anio, m)[1])
            if inicio - timedelta(days=DIAS_RADAR) <= hoy <= fin:
                return m
    return None


def revisar_radar(radar: list, fichas: list, hoy: date) -> list:
    """Notas de los festivales del radar que se acercan y el registro no tiene."""
    notas: list[Nota] = []
    cubiertos = []
    for fi in fichas:
        reciente = fi["estado"] == "terminado" and fi["hasta"] and (hoy - fi["hasta"]).days <= DIAS_MEMORIA
        if fi["estado"] in ("en-curso", "proximo") or reciente:
            f = fi["registro"]
            cubiertos.append(norm(" ".join([f.get("nombre", ""), f.get("ciclo", ""),
                                            f.get("slug", "").replace("-", " ")]
                                           + list(f.get("alias") or []))))
    for r in radar:
        nombre = r.get("nombre", "")
        slug = "radar-" + norm(nombre).replace(" ", "-")
        claves = [norm(x) for x in [nombre] + list(r.get("alias") or []) if norm(x)]
        if any(f" {k} " in f" {c} " for k in claves for c in cubiertos):
            continue
        if (r.get("ignorar_hasta") or "") >= hoy.isoformat():
            continue
        prox = r.get("proxima") or {}
        desde, hasta = _fecha(prox.get("desde") or ""), _fecha(prox.get("hasta") or "")
        donde = f", en {r['lugar']}" if r.get("lugar") else ""
        fuente = f" Fuente: {prox['fuente']}" if prox.get("fuente") else (
            f" Web: {r['web']}" if r.get("web") else "")
        if desde and (hasta or desde) >= hoy:
            # Ya anunció fechas: se cuentan los días.
            faltan = (desde - hoy).days
            cuando = rango_texto(desde, hasta)
            if faltan <= 0:
                notas.append(Nota(ERROR, slug, nombre, "radar-en-curso",
                                  f"está en curso ({cuando}{donde}) y no está en la web.{fuente}",
                                  corto=f"{cuando}, en curso"))
            elif faltan <= DIAS_URGENTE + 3:
                en = f"en {faltan} días" if faltan != 1 else "mañana"
                notas.append(Nota(ERROR, slug, nombre, "radar-inminente",
                                  f"empieza {en} ({cuando}{donde}) y no está cargado.{fuente}",
                                  corto=f"{cuando}, empieza {en}"))
            elif faltan <= 60:
                notas.append(Nota(AVISO, slug, nombre, "radar-con-fecha",
                                  f"es del {cuando}{donde} y no está cargado: sumarlo al registro "
                                  f"y cargar la grilla cuando salga.{fuente}", corto=cuando))
            continue
        # Sin edición por delante. Si la última fue hace poco, la de este año
        # ya pasó: el FESTIHUR fue del 6 al 8/11 y el registro no guarda sus
        # fechas, así que sin esto en noviembre saldría "suele ser en
        # noviembre". Un `proxima` que quedó viejo cuenta como la última.
        ult = _fecha((r.get("ultima") or {}).get("hasta") or "") or hasta or desde
        if ult and (hoy - ult).days <= DIAS_YA_FUE:
            continue
        mes = _en_ventana(r.get("meses") or [], hoy)
        if mes:
            notas.append(Nota(AVISO, slug, nombre, "radar-sin-fecha",
                              f"suele ser en {_MESES[mes - 1]}{donde} y el registro no tiene "
                              f"su próxima edición: buscar si ya anunció fechas.{fuente}",
                              corto=f"suele ser en {_MESES[mes - 1]}"))
    return notas


# ---------------------------------------------------------------------------
# La web de cada festival
# ---------------------------------------------------------------------------

def texto_de(cuerpo: str) -> list:
    """Las líneas de texto visible de una página, sin repetir y en orden."""
    cuerpo = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", cuerpo)
    cuerpo = re.sub(r"(?s)<!--.*?-->", " ", cuerpo)
    cuerpo = re.sub(r"(?i)<(?:br|/p|/div|/li|/h\d|/tr|/td|/section|/article|/a)\b[^>]*>", "\n", cuerpo)
    cuerpo = html.unescape(re.sub(r"<[^>]+>", " ", cuerpo))
    out, vistos = [], set()
    for l in cuerpo.splitlines():
        l = " ".join(l.split())
        if len(l) < 4 or l in vistos:
            continue
        vistos.add(l)
        out.append(l)
    return out


def leer_web(url: str) -> tuple[Optional[list], str]:
    """(líneas, detalle). None si no se pudo leer."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept-Language": "es-AR,es;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            cuerpo = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, type(e).__name__
    return texto_de(cuerpo), "ok"


def _huella(linea: str) -> str:
    return hashlib.sha1(linea.encode("utf-8")).hexdigest()[:8]


def revisar_webs(fichas: list, estado: dict, hoy: date, leer=leer_web,
                 avanzar: bool = True) -> tuple[list, dict]:
    """(notas, estado nuevo). Compara la web de cada festival vigente con la
    huella guardada.

    `estado`: {slug: {"url", "visto", "lineas": "h1 h2 …"}}, de
    data/festivales_web.json. `avanzar`: si lo que se ve hoy pasa a ser la
    referencia. El informe del lunes avanza; el centinela diario no, así un
    cambio del miércoles sigue a la vista hasta que el informe lo cuente.
    """
    notas: list[Nota] = []
    nuevo: dict = {}
    for fi in fichas:
        url = fi["web"]
        vigente = fi["estado"] == "en-curso" or (
            fi["estado"] == "proximo" and fi["desde"] and (fi["desde"] - hoy).days <= DIAS_WEB)
        if not url or not vigente:
            continue
        previo = estado.get(fi["slug"]) or {}
        lineas, detalle = leer(url) if leer else (None, "sin red")
        if lineas is None:
            if leer:
                notas.append(Nota(AVISO, fi["slug"], fi["nombre"], "web-no-abre",
                                  f"no se pudo leer su web ({detalle}): esta semana no se sabe "
                                  f"si cambió la grilla. {url}", efimera=True))
            if previo:
                nuevo[fi["slug"]] = previo
            continue
        huellas = [_huella(l) for l in lineas]
        if previo.get("url") == url and previo.get("lineas"):
            viejas = set(previo["lineas"].split())
            agregadas = [l for l, h in zip(lineas, huellas) if h not in viejas]
            quitadas = len(viejas - set(huellas))
            if agregadas or quitadas:
                de_grilla = [l for l in agregadas if _DE_GRILLA.search(l)]
                cerca = fi["estado"] == "en-curso" or (fi["desde"] - hoy).days <= DIAS_URGENTE
                muestra = "; ".join(f"«{l[:90]}»" for l in (de_grilla or agregadas)[:3])
                que = (f"{_n(len(agregadas), 'línea nueva', 'líneas nuevas')}" if agregadas else "") + (
                    " y " if agregadas and quitadas else "") + (
                    f"{_n(quitadas, 'que ya no está', 'que ya no están')}" if quitadas else "")
                desde = _fecha(previo.get("visto") or "")
                notas.append(Nota(
                    ERROR if (de_grilla and cerca) else AVISO, fi["slug"], fi["nombre"], "web-cambio",
                    f"su web cambió{' desde el ' + dia_mes(desde) if desde else ''}: {que}"
                    + (f". Lo nuevo: {muestra}" if muestra else "")
                    + f". Revisar la grilla contra lo cargado: {url}", efimera=True))
                if not avanzar:
                    nuevo[fi["slug"]] = previo
                    continue
            else:
                # Igual que la referencia: no se toca, así el archivo no cambia
                # (ni se commitea) los días en que no pasó nada.
                nuevo[fi["slug"]] = previo
                continue
        nuevo[fi["slug"]] = {"url": url, "visto": hoy.isoformat(), "lineas": " ".join(huellas)}
    return notas, nuevo


# ---------------------------------------------------------------------------

def cargar(root: Path) -> tuple[list, list, dict]:
    """(registro, radar, estado de las webs), cada uno vacío si falta."""
    def leer_json(nombre: str, clave: Optional[str]):
        try:
            d = json.loads((root / "data" / nombre).read_text(encoding="utf-8"))
            return d.get(clave, []) if clave else d
        except Exception:
            return [] if clave else {}
    return (leer_json("festivales.json", "festivales"),
            leer_json("festivales_radar.json", "festivales"),
            leer_json("festivales_web.json", None))
