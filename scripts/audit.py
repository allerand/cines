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
}
# Sin sonda a propósito: Cosmos (no responde a un GET pelado), Filo y Arthaus
# (listado renderizado por JS), Cacodelphia / Lugones / Borges / CEA (SPA o
# Cloudflare) y los comerciales (IMDb + La Nación, sin listing estable). Una
# sonda que siempre devuelve 0 es peor que ninguna: dispara falsas alarmas.
# Estos cines se controlan igual por su histórico de git.

SEV_ERROR, SEV_WARN, SEV_INFO = "ERROR", "AVISO", "INFO"


class Report:
    """Junta hallazgos y los imprime agrupados por severidad."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []   # (severidad, cine, mensaje)
        self.sections: list[str] = []                 # bloques de texto (tablas)

    def add(self, sev: str, cine: str, msg: str) -> None:
        self.items.append((sev, cine, msg))

    def section(self, text: str) -> None:
        self.sections.append(text)

    @property
    def n_errors(self) -> int:
        return sum(1 for s, _, _ in self.items if s == SEV_ERROR)

    def render(self) -> str:
        out: list[str] = []
        out.extend(self.sections)
        for sev, icon in ((SEV_ERROR, "🔴"), (SEV_WARN, "🟡"), (SEV_INFO, "🔵")):
            group = [(c, m) for s, c, m in self.items if s == sev]
            if not group:
                continue
            out.append(f"\n## {icon} {sev} ({len(group)})\n")
            for cine, msg in group:
                out.append(f"- **{cine}** — {msg}")
        if not self.items:
            out.append("\n✅ Sin hallazgos.")
        return "\n".join(out)


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

def check_frescura(rep: Report, meta: dict, today: date) -> None:
    raw = meta.get("updated", "")
    try:
        updated = datetime.fromisoformat(raw)
    except ValueError:
        rep.add(SEV_ERROR, "cartelera.json", f"campo `updated` ilegible: {raw!r}")
        return
    horas = (datetime.now() - updated).total_seconds() / 3600
    rep.section(f"**Última actualización:** {updated:%Y-%m-%d %H:%M} "
                f"({horas:.0f} h atrás)\n")
    # El scrape corre a diario: más de 36 h es una corrida perdida.
    if horas > 36:
        rep.add(SEV_ERROR, "cartelera.json",
                f"datos de hace {horas:.0f} h — el scrape diario no está commiteando")
    elif horas > 26:
        rep.add(SEV_WARN, "cartelera.json", f"datos de hace {horas:.0f} h")


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

    filas = []
    for cine in sorted(universo, key=lambda c: -len(fut.get(c, []))):
        ss = fut.get(cine, [])
        n, titulos = len(ss), len({s.get("title_es", "") for s in ss})
        base = baseline.get(cine)
        probe_n, probe_detail = probes.get(cine, (None, ""))
        filas.append((cine, n, titulos, base, probe_n))

        es_comercial = cine.startswith(COMMERCIAL_PREFIXES)
        rancio = False

        if n == 0:
            if probe_n:
                rep.add(SEV_ERROR, cine,
                        f"0 funciones, pero la fuente publica {probe_n} {probe_detail} "
                        f"→ el scraper se rompió")
            elif base:
                rep.add(SEV_ERROR, cine,
                        f"0 funciones (venía de ~{base:.0f}/día) → caído")
            elif probe_n == 0:
                rep.add(SEV_INFO, cine, "0 funciones y la fuente tampoco publica nada")
            else:
                rep.add(SEV_WARN, cine, "0 funciones y no se pudo sondear la fuente")
            continue

        if es_comercial and titulos < COMMERCIAL_MIN_TITLES:
            rancio = True
            rep.add(SEV_ERROR, cine,
                    f"sólo {titulos} título(s) distinto(s) en {n} funciones — una sala "
                    f"de cadena nunca tiene tan poco: se está publicando data vieja "
                    f"preservada por la merge")

        # Caída brusca contra su propio histórico. Si ya saltó la regla de
        # títulos, la caída es el mismo problema contado dos veces.
        if not rancio and base and base >= 5 and n < base * 0.4:
            rep.add(SEV_WARN, cine,
                    f"{n} funciones vs. ~{base:.0f} habituales (caída del "
                    f"{100 - n / base * 100:.0f}%)")

        if probe_n and titulos and probe_n >= titulos * 3 and probe_n - titulos >= 4:
            rep.add(SEV_WARN, cine,
                    f"la fuente publica {probe_n} {probe_detail} y sólo tenemos "
                    f"{titulos} título(s) — puede faltar programación")

    # Tabla de cobertura
    head = (f"\n| Cine | Funciones | Títulos | Histórico/día | Fuente |\n"
            f"|---|---:|---:|---:|---:|")
    body = "\n".join(
        f"| {c} | {n} | {t} | {'—' if b is None else f'{b:.0f}'} | "
        f"{'—' if p is None else p} |"
        for c, n, t, b, p in filas)
    rep.section(head + "\n" + body + "\n")


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
        # cortos son varias películas en la misma función, a propósito.
        key = (cine, fecha, hora)
        ciclo = (s.get("ciclo") or "").strip()
        if key in vistos:
            prev_titulo, prev_ciclo = vistos[key]
            if prev_titulo != titulo and not (ciclo and ciclo == prev_ciclo):
                flag("dos títulos en el mismo horario", cine,
                     f"{fecha} {hora}: {prev_titulo!r} vs {titulo!r}")
        vistos[key] = (titulo, ciclo)

    for (regla, cine), n in sorted(problemas.items(), key=lambda kv: -kv[1]):
        muestra = "; ".join(ejemplos[(regla, cine)])
        sev = SEV_ERROR if regla in ("título vacío", "hora inválida",
                                     "director duplicado",
                                     "título con copete pegado") else SEV_WARN
        rep.add(sev, cine, f"{regla} ×{n} — {muestra}")


def check_completitud(rep: Report, screenings: list[dict], today: date) -> None:
    """Campos que no rompen nada pero degradan la ficha (y el post de IG)."""
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    por_cine = defaultdict(list)
    for s in fut:
        por_cine[s["cine"]].append(s)
    for cine, ss in sorted(por_cine.items()):
        sin_dir = sum(1 for s in ss if not (s.get("director") or "").strip())
        sin_lb = sum(1 for s in ss if not (s.get("letterboxd") or "").strip())
        if sin_dir and sin_dir / len(ss) > 0.5:
            rep.add(SEV_WARN, cine, f"{sin_dir}/{len(ss)} funciones sin director")
        if sin_lb and sin_lb / len(ss) > 0.6:
            rep.add(SEV_INFO, cine, f"{sin_lb}/{len(ss)} funciones sin link de Letterboxd")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="sin sondas HTTP")
    ap.add_argument("--out", type=Path, help="escribe el informe en un archivo")
    ap.add_argument("--dias-historico", type=int, default=14,
                    help="snapshots de git para la línea de base (default 14)")
    args = ap.parse_args()

    meta, screenings = load_cartelera()
    today = date.today()
    rep = Report()

    rep.section(f"# Auditoría de cartelera — {today:%Y-%m-%d}\n")

    check_frescura(rep, meta, today)

    snaps = git_snapshots(args.dias_historico)
    if not snaps:
        rep.add(SEV_INFO, "auditoría",
                "sin línea de base histórica (clone shallow o repo sin historia): "
                "usá actions/checkout con fetch-depth: 0")

    cines_hoy = {s["cine"] for s in screenings}
    a_sondear = sorted(set(PROBES) | cines_hoy & set(PROBES))
    probes = {} if args.offline else run_probes(a_sondear)

    check_cobertura(rep, screenings, today, snaps, probes)
    check_calidad(rep, screenings, today)
    check_completitud(rep, screenings, today)

    informe = rep.render()
    print(informe)
    if args.out:
        args.out.write_text(informe + "\n", encoding="utf-8")

    return 1 if rep.n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
