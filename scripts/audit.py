#!/usr/bin/env python3
"""
Auditoría de la cartelera: detecta cines caídos, funciones faltantes y datos
sucios. Pensada para correr todas las semanas (ver .github/workflows/audit.yml
o el skill /auditoria) y devolver un informe corto y accionable.

Por qué existe: cada scraper de scraper.py atrapa sus excepciones y devuelve
[] — si una fuente cambia de HTML o tarda de más, el cine desaparece de la web
en silencio. Nada falla, nada avisa: la grilla simplemente queda incompleta.
Esta auditoría es el chequeo que convierte ese silencio en un informe.

Tres frentes:
  1. Frescura      — hace cuánto no se actualiza cartelera.json.
  2. Cobertura     — funciones por cine vs. su propio histórico (git) y vs. lo
                     que hoy publica la fuente (sondas HTTP).
  3. Calidad       — campos sucios (director duplicado, título que es el copete
                     del ciclo, horas inválidas, duplicados, años imposibles).

Sólo stdlib: corre con cualquier Python 3.8+ sin instalar nada.

Uso:
    python3 scripts/audit.py                 # informe completo
    python3 scripts/audit.py --offline       # sin sondas HTTP (rápido)
    python3 scripts/audit.py --out audit.md  # además escribe el informe
Sale con código 1 si hay hallazgos de nivel ERROR (para que CI falle).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
CARTELERA = ROOT / "data" / "cartelera.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Cines de cadena: la merge de run.py preserva sus funciones futuras entre
# corridas, así que un scraper roto no los baja a cero — los deja rancios, con
# cada vez menos títulos. Por eso se los mide por CANTIDAD DE TÍTULOS y no por
# cantidad de funciones.
COMMERCIAL_PREFIXES = ("Cinemark", "Hoyts", "Cinépolis", "Cinepolis", "Showcase", "Multiplex")
# Una sala de cadena en cartelera nunca tiene menos de esto. Con 1-2 títulos lo
# que estamos publicando es el resto de un scrape viejo. El umbral va bajo a
# propósito: en una semana floja las cadenas comparten 5 estrenos y de nada
# sirve una alarma que salta sola.
COMMERCIAL_MIN_TITLES = 3

# Sondas: página que lista la programación + patrón de los ítems. No parsean la
# grilla (eso es trabajo del scraper), sólo responden "¿la fuente tiene algo
# publicado?". Sirven para distinguir "el cine no programó nada" de "el scraper
# se rompió". Los cines sin sonda (SPA que requieren JS, o APIs con token) se
# controlan igual por el histórico de git.
PROBES = {
    "MALBA":                    ("https://malba.org.ar/cine/", r"/evento/[a-z0-9\-]+"),
    "CCK":                      ("https://palaciolibertad.gob.ar/cine/", r"/events/[a-z0-9\-]+"),
    "Centro Cultural 25 de Mayo": ("https://cc25.org/cine/", r"/eventos/[a-z0-9\-]+"),
    "Biblioteca Nacional":      ("https://www.bn.gov.ar/agenda-cultural?categoria=cine",
                                 r"/agenda-cultural/[a-z0-9\-]+"),
    "Biblioteca del Congreso":  ("https://bcn.gob.ar/agenda/cine", r"/cine/[a-z0-9\-]+"),
    "Cine Gaumont":             ("https://www.cinegaumont.ar/Default", r"filmid=(\d+)"),
    "Casa del Bicentenario":    ("https://casadelbicentenario.cultura.gob.ar/actividades/",
                                 r"/actividad/[a-z0-9\-]+"),
    "Amorina":                  ("https://www.amorina.club/schedule.json", "@amorina"),
    "Archivo General de la Nación": ("https://www.argentina.gob.ar/interior/"
                                     "archivo-general-de-la-nacion/"
                                     "cine-en-el-archivo-general-de-la-nacion",
                                     "@agn"),
}
# Sin sonda a propósito: Cosmos (no responde a un GET pelado), Filo y Arthaus
# (listado renderizado por JS), Lugones / Borges / CEA (SPA o Cloudflare),
# Cacodelphia (su fuente es el newsletter que llega por mail, no una URL que se
# pueda sondear) y los comerciales (IMDb + La Nación, sin listing estable). Una
# sonda que siempre devuelve 0 es peor que ninguna: dispara falsas alarmas.
# Estos cines se controlan igual por su histórico de git.

# Cines donde la sonda cuenta más ítems de los que hay programados, porque la
# listing mezcla vigentes con un archivo de funciones viejas. Comparar contra
# ese número dispara "puede faltar programación" todas las semanas, y una
# alarma que siempre suena deja de leerse. El chequeo de cine caído (0
# funciones) les sigue aplicando igual.
SIN_REGLA_FALTANTES = {"Centro Cultural 25 de Mayo"}

# Sonda del AGN (ver probe(): "@agn"). Cada función es un <strong>título</strong>
# seguido de un <br> y la línea "Jueves 6 de agosto | 70 min. | …".
_AGN_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_AGN_FILM_RE = re.compile(
    r"<strong>([^<>]{3,80})</strong>\s*<br\s*/?>\s*"
    r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[áa]bado|domingo)?\s*"
    r"(\d{1,2})\s+de\s+(" + "|".join(_AGN_MESES) + r")",
    re.IGNORECASE)

SEV_ERROR, SEV_WARN, SEV_INFO = "ERROR", "AVISO", "INFO"


class Report:
    """Junta los hallazgos y arma un informe que se lee de arriba hacia abajo.

    El orden importa más que la completitud: primero el veredicto, después lo
    que hay que tocar esta semana, después lo que cambió, y recién al final lo
    que viene arrastrándose hace rato. Un informe que empieza con una tabla de
    treinta filas no se lee.
    """

    def __init__(self) -> None:
        self.accion: list[tuple[str, str]] = []    # (cine, qué hacer) — ERRORes
        self.cronico: list[str] = []               # frases ya resumidas
        self.cambios: list[str] = []               # diff contra la semana pasada
        self.contexto = ""                         # línea de estado
        self.tabla: list[tuple] = []               # sólo cines con algo que mirar
        self.sin_novedad = 0

    def accionar(self, cine: str, msg: str) -> None:
        self.accion.append((cine, msg))

    def cronicar(self, msg: str) -> None:
        self.cronico.append(msg)

    def cambiar(self, msg: str) -> None:
        self.cambios.append(msg)

    @property
    def n_errors(self) -> int:
        return len(self.accion)

    @property
    def veredicto(self) -> str:
        if not self.accion:
            return "✅ Todo en orden"
        cines = {c for c, _ in self.accion}
        if len(cines) == 1:
            return f"🔴 Hay algo para mirar en {next(iter(cines))}"
        return f"🔴 Hay {len(self.accion)} cosas para mirar en {len(cines)} cines"

    def render(self, hoy: date) -> str:
        out = [f"# Auditoría de la cartelera — {_fecha_larga(hoy)}", "",
               f"## {self.veredicto}", "", self.contexto, ""]

        if self.accion:
            out += ["## Para mirar esta semana", ""]
            out += [f"- **{cine}** — {msg}" for cine, msg in self.accion]
            out.append("")

        out += ["## Qué cambió desde la semana pasada", ""]
        out += [f"- {c}" for c in self.cambios] if self.cambios else \
               ["Nada raro: ningún cine se cayó ni pegó un salto respecto de "
                "la semana pasada."]
        out.append("")

        if self.tabla:
            out += ["## Cines por debajo de lo habitual", "",
                    "| Cine | Funciones | Títulos | Habitual |", "|---|---:|---:|---:|"]
            out += [f"| {c} | {n} | {t} | {b} |" for c, n, t, b in self.tabla]
            out += ["", f"Los otros {self.sin_novedad} cines están en su rango normal.", ""]

        if self.cronico:
            out += ["## Pendientes de siempre", "",
                    "Cosas que no rompen la web pero degradan la ficha. "
                    "Están acá para que no se olviden, no para arreglarlas hoy.", ""]
            out += [f"- {c}" for c in self.cronico]
            out.append("")

        out += ["---", "",
                "Generado por `scripts/audit.py`. Para correrlo a mano: "
                "`cd ~/cines && python3 scripts/audit.py`"]
        return "\n".join(out)

    def asunto(self, hoy: date) -> str:
        return f"{self.veredicto} — cartelera al {hoy:%d/%m}"


_MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fecha_larga(d: date) -> str:
    return f"{_DIAS_LARGO[d.weekday()]} {d.day} de {_MESES_LARGO[d.month - 1]}"


# Conversor markdown → HTML para el subconjunto que usa el informe (títulos,
# tabla, viñetas, negrita, code). Es para el mail: el cuerpo tiene que verse
# bien en un cliente de correo, y no vale la pena meter una dependencia ni
# reescribir el render entero — el markdown sigue siendo la fuente única.
def md_a_html(md: str) -> str:
    css = {
        SEV_ERROR: "#d93025", SEV_WARN: "#b06000", SEV_INFO: "#1a73e8",
    }
    def inline(t: str) -> str:
        t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        return re.sub(r"`(.+?)`", r"<code>\1</code>", t)

    out: list[str] = []
    en_lista = en_tabla = False
    color = "#1a1a1a"
    for linea in md.splitlines():
        l = linea.rstrip()
        es_fila = l.startswith("|")
        if en_lista and not l.startswith("- "):
            out.append("</ul>"); en_lista = False
        if en_tabla and not es_fila:
            out.append("</table>"); en_tabla = False
        if not l:
            continue
        if l.startswith("## "):
            texto = l[3:]
            color = next((c for s, c in css.items() if s in texto), "#1a1a1a")
            out.append(f'<h3 style="color:{color};margin:22px 0 8px;font-size:16px">'
                       f'{inline(texto)}</h3>')
        elif l.startswith("# "):
            out.append(f'<h2 style="margin:0 0 6px;font-size:20px">{inline(l[2:])}</h2>')
        elif es_fila:
            celdas = [c.strip() for c in l.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                continue          # separador de encabezado
            if not en_tabla:
                out.append('<table style="border-collapse:collapse;font-size:13px;'
                           'margin:8px 0">')
                en_tabla = True
                out.append("<tr>" + "".join(
                    f'<th style="text-align:left;padding:3px 10px 3px 0;'
                    f'border-bottom:1px solid #ddd">{inline(c)}</th>'
                    for c in celdas) + "</tr>")
                continue
            out.append("<tr>" + "".join(
                f'<td style="padding:2px 10px 2px 0;border-bottom:1px solid #f0f0f0">'
                f'{inline(c)}</td>' for c in celdas) + "</tr>")
        elif l.startswith("- "):
            if not en_lista:
                out.append('<ul style="margin:0 0 4px;padding-left:18px;font-size:14px">')
                en_lista = True
            out.append(f"<li style='margin-bottom:4px'>{inline(l[2:])}</li>")
        else:
            out.append(f'<p style="margin:0 0 10px;font-size:14px">{inline(l)}</p>')
    if en_lista:
        out.append("</ul>")
    if en_tabla:
        out.append("</table>")
    return ('<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
            "Helvetica,Arial,sans-serif;max-width:680px;color:#1a1a1a;"
            'line-height:1.5">' + "\n".join(out) + "</div>")


# --------------------------------------------------------------------------
# Carga de datos
# --------------------------------------------------------------------------

def load_cartelera() -> tuple[dict, list[dict]]:
    data = json.loads(CARTELERA.read_text(encoding="utf-8"))
    return data, data.get("screenings", [])


def git_snapshots(n_days: int = 14) -> dict[str, Counter]:
    """Último commit de cada uno de los últimos n_days días que tocó
    cartelera.json → Counter de funciones futuras por cine en ese momento.

    Es la línea de base: un cine que venía trayendo 20 funciones por día y hoy
    trae 0 está roto, aunque el scraper no haya tirado ningún error. Devuelve
    {} si el repo es un clone shallow (CI sin fetch-depth: 0) o no hay git.
    """
    try:
        log = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--format=%H %ad",
             "--date=format:%Y-%m-%d", "--", "data/cartelera.json"],
            capture_output=True, text=True, timeout=30, check=True).stdout
    except Exception:
        return {}

    seen: set[str] = set()
    commits: list[tuple[str, str]] = []
    for line in log.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, day = parts
        if day in seen:
            continue
        seen.add(day)
        commits.append((day, sha))
        if len(commits) >= n_days:
            break

    if len(commits) < 3:   # historia insuficiente → sin baseline
        return {}

    snaps: dict[str, Counter] = {}
    for day, sha in commits:
        try:
            blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:data/cartelera.json"],
                                  capture_output=True, text=True, timeout=30, check=True).stdout
            payload = json.loads(blob)
        except Exception:
            continue
        # Sólo funciones futuras respecto de ESE día: así la comparación entre
        # snapshots no se contamina con el largo de la ventana.
        snaps[day] = Counter(s["cine"] for s in payload.get("screenings", [])
                             if s.get("fecha", "") >= day)
    return snaps


# --------------------------------------------------------------------------
# Sondas en vivo
# --------------------------------------------------------------------------

def probe(cine: str, url: str, pattern: str) -> tuple[str, int | None, str]:
    """(cine, cantidad de ítems publicados, detalle). None = no se pudo medir."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return cine, None, f"HTTP {e.code}"
    except Exception as e:
        return cine, None, f"{type(e).__name__}"

    if pattern == "@amorina":
        # schedule.json: contamos funciones futuras de verdad, no links.
        try:
            items = json.loads(body)
        except Exception:
            return cine, None, "JSON inválido"
        today = date.today().isoformat()
        n = 0
        for it in items if isinstance(items, list) else []:
            st = (it.get("showtime") or "")[:10]
            if st >= today:
                n += 1
        return cine, n, "funciones futuras en schedule.json"

    if pattern == "@agn":
        # El AGN no tiene listing: es una landing que reescriben cada mes y que
        # conserva las funciones ya pasadas hasta que sube el ciclo siguiente.
        # Contar títulos a secas diría "la fuente publica 3" a fin de mes, con
        # la cartelera legítimamente vacía, y el informe cerraría cada mes con
        # un "el scraper se rompió" que no es cierto. Contamos sólo lo que
        # todavía no pasó.
        anio = re.search(r"Fecha\s*:.{0,80}?\bde\s+(20\d{2})",
                         re.sub(r"<[^>]+>", " ", body), re.IGNORECASE)
        anio = int(anio.group(1)) if anio else date.today().year
        n = 0
        for _, dia, mes in _AGN_FILM_RE.findall(body):
            try:
                d = date(anio, _AGN_MESES[mes.lower()], int(dia))
            except ValueError:
                continue
            if d >= date.today():
                n += 1
        return cine, n, "funciones futuras en la landing"

    return cine, len(set(re.findall(pattern, body))), "ítems en la listing"


def run_probes(cines: list[str]) -> dict[str, tuple[int | None, str]]:
    jobs = [(c, *PROBES[c]) for c in cines if c in PROBES]
    out: dict[str, tuple[int | None, str]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for cine, n, detail in pool.map(lambda a: probe(*a), jobs):
            out[cine] = (n, detail)
    return out


# --------------------------------------------------------------------------
# Chequeos
# --------------------------------------------------------------------------

def check_frescura(rep: Report, meta: dict, screenings: list[dict],
                   today: date) -> None:
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    cines = len({s["cine"] for s in fut})

    raw = meta.get("updated", "")
    try:
        updated = datetime.fromisoformat(raw)
    except ValueError:
        rep.accionar("cartelera.json", f"el campo `updated` quedó ilegible: {raw!r}")
        rep.contexto = f"{cines} cines · {len(fut)} funciones publicadas."
        return

    horas = (datetime.now() - updated).total_seconds() / 3600
    rep.contexto = (f"Datos de hace {horas:.0f} h · {cines} cines · "
                    f"{len(fut)} funciones publicadas.")
    # El scrape corre a diario: más de 36 h es una corrida perdida.
    if horas > 36:
        rep.accionar("El scrape diario",
                     f"los datos son de hace {horas:.0f} h — el workflow "
                     f"`scrape.yml` no está commiteando. Mirá la última corrida "
                     f"en Actions.")


def check_cobertura(rep: Report, screenings: list[dict], today: date,
                    snaps: dict[str, Counter], probes: dict) -> None:
    hoy = today.isoformat()
    fut = defaultdict(list)
    for s in screenings:
        if s.get("fecha", "") >= hoy:
            fut[s["cine"]].append(s)

    # Universo de cines: los de hoy + los del histórico + los que tienen sonda.
    # Un cine que desapareció del todo es el caso más grave, y sin esta unión
    # pasaría inadvertido — incluir los sondeados cubre además a los que ya
    # llevan más días caídos que la ventana del histórico.
    universo = set(fut) | {c for snap in snaps.values() for c in snap} | set(PROBES)
    baseline = {
        c: median([snap.get(c, 0) for snap in snaps.values()])
        for c in universo
    } if snaps else {}

    flojos = []
    for cine in sorted(universo, key=lambda c: -len(fut.get(c, []))):
        ss = fut.get(cine, [])
        n, titulos = len(ss), len({s.get("title_es", "") for s in ss})
        base = baseline.get(cine)
        probe_n, probe_detail = probes.get(cine, (None, ""))

        es_comercial = cine.startswith(COMMERCIAL_PREFIXES)
        rancio = False

        if n == 0:
            if probe_n:
                rep.accionar(cine, f"no tiene ninguna función en la web, pero la "
                                   f"fuente publica {probe_n} {probe_detail}. El "
                                   f"scraper se rompió.")
            elif base:
                rep.accionar(cine, f"se quedó sin funciones (venía de unas "
                                   f"{base:.0f} por día). Revisá su scraper.")
            # Si la fuente tampoco publica nada, el cine simplemente no
            # programó: no es un hallazgo, es la realidad.
            continue

        if es_comercial and titulos < COMMERCIAL_MIN_TITLES:
            rancio = True
            rep.accionar(cine, f"sólo {titulos} película(s) distinta(s) en {n} "
                               f"funciones. Una sala de cadena nunca tiene tan "
                               f"poco: se está publicando data vieja.")

        # Caída brusca contra su propio histórico. No aplica a las cadenas: La
        # Nación publica sólo el día de hoy para las que no son del grupo
        # Cinemark Hoyts, así que su número es estructuralmente más chico que
        # el histórico y la alarma saltaría todas las semanas.
        if not rancio and not es_comercial and base and base >= 5 and n < base * 0.4:
            flojos.append((cine, n, titulos, f"~{base:.0f}"))

        if (cine not in SIN_REGLA_FALTANTES and probe_n and titulos
                and probe_n >= titulos * 3 and probe_n - titulos >= 4):
            rep.accionar(cine, f"la fuente publica {probe_n} {probe_detail} y "
                               f"nosotros tenemos {titulos} película(s). Puede "
                               f"estar faltando programación.")

    rep.tabla = flojos
    rep.sin_novedad = len([c for c in universo if fut.get(c)]) - len(flojos)


def check_cambios(rep: Report, screenings: list[dict], today: date,
                  snaps: dict[str, Counter]) -> None:
    """Diff contra el snapshot de hace una semana.

    Es la sección que de verdad se lee: un informe semanal sirve por lo que
    cambió, no por el estado absoluto. Un cine que viene con 3 funciones hace
    meses no es noticia; uno que pasó de 20 a 0 la semana pasada, sí.
    """
    if not snaps:
        return
    hoy = today.isoformat()
    objetivo = (today - timedelta(days=7)).isoformat()
    # El snapshot más cercano a hace 7 días.
    dia_ref = min(snaps, key=lambda d: abs((date.fromisoformat(d) - date.fromisoformat(objetivo)).days))
    if abs((date.fromisoformat(dia_ref) - date.fromisoformat(objetivo)).days) > 3:
        return          # sin histórico comparable, mejor no inventar un diff

    antes = snaps[dia_ref]
    ahora = Counter(s["cine"] for s in screenings if s.get("fecha", "") >= hoy)

    # Prioridad por gravedad, no por tamaño: que un cine se caiga importa más
    # que uno que duplicó funciones, aunque el salto sea más chico.
    cambios: list[tuple[int, int, str]] = []
    for cine in set(antes) | set(ahora):
        a, b = antes.get(cine, 0), ahora.get(cine, 0)
        delta = abs(b - a)
        if b == 0 and a > 0:
            cambios.append((0, delta, f"**{cine}** desapareció: {a} → 0 funciones."))
        elif a >= 8 and b < a * 0.5:
            cambios.append((1, delta, f"**{cine}** bajó bastante: {a} → {b} funciones."))
        elif a == 0 and b > 0:
            cambios.append((2, delta, f"**{cine}** volvió a la cartelera: 0 → {b} funciones."))
        elif a >= 8 and b > a * 2:
            cambios.append((3, delta, f"**{cine}** subió bastante: {a} → {b} funciones."))

    cambios.sort(key=lambda c: (c[0], -c[1]))
    TOPE = 8
    for _, _, msg in cambios[:TOPE]:
        rep.cambiar(msg)
    if len(cambios) > TOPE:
        rep.cambiar(f"…y {len(cambios) - TOPE} cines más con cambios de tamaño "
                    f"parecido (corré `python3 scripts/audit.py` para verlos).")


# Un director es un nombre, no una oración. Estas señales delatan que el parser
# se llevó el copete, la sinopsis o el nombre del ciclo en vez del crédito.
_DIR_FRASE = re.compile(r"\b(será|sera|proyecc|festival|presenta|con la|marco de|"
                        r"ciclo|entrada|función|funcion)\b", re.IGNORECASE)


def check_calidad(rep: Report, screenings: list[dict], today: date) -> None:
    hoy = today.isoformat()
    anio_max = today.year + 2
    vistos: dict[tuple, tuple[str, str]] = {}
    problemas: Counter = Counter()
    ejemplos: dict[str, list[str]] = defaultdict(list)

    def flag(regla: str, cine: str, detalle: str) -> None:
        problemas[(regla, cine)] += 1
        if len(ejemplos[(regla, cine)]) < 3:
            ejemplos[(regla, cine)].append(detalle)

    for s in screenings:
        cine = s.get("cine", "?")
        titulo = (s.get("title_es") or "").strip()
        director = (s.get("director") or "").strip()
        fecha, hora = s.get("fecha", ""), s.get("hora", "")

        if fecha < hoy:
            continue    # las pasadas ya no se muestran; no vale la pena auditarlas

        # Director repetido: "X De X De X" (MALBA repite el crédito en el HTML).
        if re.search(r"^(.+?)\s+[Dd]e\s+\1\b", director):
            flag("director duplicado", cine, f"{titulo}: {director!r}")
        elif _DIR_FRASE.search(director) or (
                len(director.split()) > 7 and "," not in director):
            # La coma exime a los repartos legítimos de directores (los cortos
            # de festival y las antologías tipo "Heavy Metal" traen diez).
            flag("director que no es un nombre", cine, f"{titulo}: {director!r}")

        # Título que en realidad es el copete/ciclo de la card.
        if "·" in titulo or len(titulo) > 80:
            flag("título con copete pegado", cine, repr(titulo))
        elif titulo.isupper() and len(titulo) > 3:
            flag("título todo en mayúsculas", cine, repr(titulo))
        elif not titulo:
            flag("título vacío", cine, f"{fecha} {hora}")

        if not re.fullmatch(r"[0-2]\d:[0-5]\d", hora):
            flag("hora inválida", cine, f"{titulo}: {hora!r}")

        anio = s.get("year")
        if isinstance(anio, int) and not (1888 <= anio <= anio_max):
            flag("año imposible", cine, f"{titulo}: {anio}")

        dur = s.get("duration")
        if isinstance(dur, int) and not (1 <= dur <= 600):
            flag("duración imposible", cine, f"{titulo}: {dur} min")

        url = s.get("ticket_url") or ""
        if not url.startswith("http"):
            flag("ticket_url inválido", cine, f"{titulo}: {url!r}")

        # Misma sala, misma fecha y hora, dos títulos distintos: síntoma de una
        # card mal delimitada. No aplica si comparten ciclo — un programa de
        # cortos son varias películas en la misma función, a propósito — ni en
        # los multiplex, que tienen diez salas y estrenan todo a la misma hora.
        key = (cine, fecha, hora)
        ciclo = (s.get("ciclo") or "").strip()
        if cine.startswith(COMMERCIAL_PREFIXES):
            continue
        if key in vistos:
            prev_titulo, prev_ciclo = vistos[key]
            if prev_titulo != titulo and not (ciclo and ciclo == prev_ciclo):
                flag("dos títulos en el mismo horario", cine,
                     f"{fecha} {hora}: {prev_titulo!r} vs {titulo!r}")
        vistos[key] = (titulo, ciclo)

    # Reglas que rompen la ficha publicada → acción. El resto se resume abajo:
    # son cosas que vienen arrastrándose y que ver una vez alcanza.
    QUE_HACER = {
        "título vacío": "hay funciones sin título",
        "hora inválida": "hay horarios que no se pudieron parsear",
        "director duplicado": "el crédito viene repetido desde la fuente",
        "título con copete pegado": "el título en realidad es el copete del "
                                    "ciclo o una actividad, no una película",
    }
    for (regla, cine), n in sorted(problemas.items(), key=lambda kv: -kv[1]):
        muestra = ejemplos[(regla, cine)][0]
        if regla in QUE_HACER:
            veces = f" (×{n})" if n > 1 else ""
            rep.accionar(cine, f"{QUE_HACER[regla]}{veces}. Ejemplo: {muestra}")
        else:
            rep.cronicar(f"**{cine}**: {regla} ×{n}.")


def check_completitud(rep: Report, screenings: list[dict], today: date) -> None:
    """Campos que no rompen nada pero degradan la ficha (y el post de IG)."""
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    por_cine = defaultdict(list)
    for s in fut:
        por_cine[s["cine"]].append(s)
    # Se resume por campo y no por cine: siete líneas diciendo "sin Letterboxd"
    # no dicen más que una que los liste.
    for campo, etiqueta, umbral in (("director", "sin director", 0.5),
                                    ("letterboxd", "sin link de Letterboxd", 0.6)):
        afectados = []
        total = 0
        for cine, ss in sorted(por_cine.items()):
            faltan = sum(1 for s in ss if not (s.get(campo) or "").strip())
            if faltan and faltan / len(ss) > umbral:
                afectados.append(f"{cine} ({faltan}/{len(ss)})")
                total += faltan
        if afectados:
            rep.cronicar(f"{total} funciones {etiqueta}: {', '.join(afectados)}.")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="sin sondas HTTP")
    ap.add_argument("--out", type=Path, help="escribe el informe en un archivo")
    ap.add_argument("--html", type=Path,
                    help="además escribe el informe en HTML (para el mail semanal)")
    ap.add_argument("--dias-historico", type=int, default=14,
                    help="snapshots de git para la línea de base (default 14)")
    args = ap.parse_args()

    meta, screenings = load_cartelera()
    today = date.today()
    rep = Report()

    check_frescura(rep, meta, screenings, today)

    snaps = git_snapshots(args.dias_historico)
    if not snaps:
        rep.cronicar("Sin línea de base histórica: el repo está clonado shallow. "
                     "En CI hace falta `actions/checkout` con `fetch-depth: 0`.")

    cines_hoy = {s["cine"] for s in screenings}
    a_sondear = sorted(set(PROBES) | cines_hoy & set(PROBES))
    probes = {} if args.offline else run_probes(a_sondear)

    check_cobertura(rep, screenings, today, snaps, probes)
    check_cambios(rep, screenings, today, snaps)
    check_calidad(rep, screenings, today)
    check_completitud(rep, screenings, today)

    informe = rep.render(today)
    print(informe)
    if args.out:
        args.out.write_text(informe + "\n", encoding="utf-8")
    if args.html:
        # Asunto y fecha van en comentarios HTML para que el Apps Script que
        # manda el mail no tenga que re-parsear el informe.
        args.html.write_text(
            f"<!-- asunto: {rep.asunto(today)} -->\n"
            f"<!-- fecha: {today.isoformat()} -->\n"
            + md_a_html(informe) + "\n",
            encoding="utf-8")

    return 1 if rep.n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
