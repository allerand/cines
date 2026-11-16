#!/usr/bin/env python3
"""
Auditoría de la cartelera: detecta cines caídos, funciones faltantes, datos
sucios o en el casillero equivocado y festivales desatendidos. Corre todos los
lunes (.github/workflows/audit.yml), todos los días en modo centinela, y a
mano con el skill /auditoria. Devuelve un informe corto y accionable.

Por qué existe: cada scraper de scraper.py atrapa sus excepciones y devuelve
[] — si una fuente cambia de HTML o tarda de más, el cine desaparece de la web
en silencio. Nada falla, nada avisa: la grilla simplemente queda incompleta.
Esta auditoría es el chequeo que convierte ese silencio en un informe.

Cómo está armada: cinco agentes, cada uno con una sola cosa a cargo. Todos
entregan su parte en cada corrida, aunque no tengan nada que decir, y si uno
no puede terminar, eso mismo es un hallazgo: lo que no se revisó no pasa por
revisado.

  frescura    que el scrape corra todos los días y las stories salgan
  fuentes     que ninguna sala se caiga, se quede corta o viva de caché, en
              Buenos Aires y en Madrid (audit_fuentes.py)
  categorias  que cada dato esté en su casillero: película, ciclo, director,
              sala (categorias.py, en la raíz, que también usa run.py)
  festivales  que ninguno se pase y que los cargados sigan al día
              (audit_festivales.py)
  fichas      que cada función tenga sus datos y estén bien escritos

Lo que hace que nada se pierda de una semana a la otra:

  - data/audit.json guarda qué hallazgos están abiertos y desde cuándo. El
    informe separa lo nuevo de lo que sigue abierto, dice hace cuánto, y
    cuenta lo que se resolvió.
  - data/audit_excepciones.json es lo que ya se miró y se aceptó, con su
    motivo. Una alarma que suena todas las semanas deja de leerse.
  - --centinela corre todos los días y manda un mail sólo si apareció un
    ERROR que ayer no estaba.

Los mismos cinco nombres tienen los agentes de Claude que resuelven lo que
esto encuentra (.claude/agents/, los coordina el skill /auditoria): acá se
detecta, allá se confirma contra la fuente y se arregla.

Sólo stdlib: corre con cualquier Python 3.8+ sin instalar nada.

Uso:
    python3 scripts/audit.py                   # informe completo, sin escribir nada
    python3 scripts/audit.py --offline         # sin red (sondas, webs, Actions)
    python3 scripts/audit.py --out data/audit.md --html data/audit.html \\
                             --json data/audit.json       # lo que corre el lunes
    python3 scripts/audit.py --centinela --json data/audit.json --alerta a.html
    python3 scripts/audit.py --como-si-fuera 2026-11-15   # con la cartelera de ese día
Sale con código 1 si hay hallazgos de nivel ERROR (para que CI falle).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import categorias                                      # noqa: E402
import audit_festivales as monitor                     # noqa: E402
import audit_fuentes as tablero_mod                    # noqa: E402
from audit_fuentes import Historia, chispa, dias_entre  # noqa: E402
from categorias import COMMERCIAL_PREFIXES             # noqa: E402

CARTELERA = ROOT / "data" / "cartelera.json"
ESTADO = ROOT / "data" / "audit.json"
EXCEPCIONES = ROOT / "data" / "audit_excepciones.json"
WEBS = ROOT / "data" / "festivales_web.json"

# Una cartelera por ciudad. Madrid tiene su propio archivo (run.py reparte con
# CINES_MADRID), así que se audita aparte y se informa aparte.
CIUDADES = {
    "ba":     ("Buenos Aires", "data/cartelera.json"),
    "madrid": ("Madrid", "data/cartelera-madrid.json"),
}

# Los agentes: nombre para el informe y qué cuida cada uno.
AGENTES = {
    "frescura":   ("Frescura", "que el scrape corra todos los días y las stories salgan"),
    "fuentes":    ("Fuentes", "que ninguna sala se caiga, se quede corta o viva de caché"),
    "categorias": ("Categorías", "que cada dato esté en su casillero: película, ciclo, director, sala"),
    "festivales": ("Festivales", "que ninguno se pase y que los cargados sigan al día"),
    "fichas":     ("Fichas", "que cada función tenga sus datos y estén bien escritos"),
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Cines de cadena (COMMERCIAL_PREFIXES, de categorias.py): la merge de run.py
# preserva sus funciones futuras entre corridas, así que un scraper roto no los
# baja a cero: los deja rancios, con cada vez menos títulos. Por eso se los
# mide por CANTIDAD DE TÍTULOS y no por cantidad de funciones.
#
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
    "CEA":                      ("https://cea.mda.gob.ar/", "@cea"),
    # La home de la ticketera lista TODO lo que programa la sala, no sólo cine
    # (hay ciclos de charlas y música), así que el número es una cota superior
    # de las funciones que nos corresponden. Sirve igual para lo que importa:
    # si da 0, el que se rompió es el scraper o la fuente, no la programación.
    "Sala Lúcida":              ("https://portal.salalucida.org/",
                                 r"/eventos/[a-z0-9\-]+"),
    # Cuenta eventos por venir, no funciones: una doble función es un evento
    # con dos. Ver probe(): "@farus".
    "Cineclub Farus":           ("https://centralticket.net/search?q=farus", "@farus"),
    # La agenda filtrada por "Tipo de evento: Cine". Cuenta eventos vigentes,
    # no funciones: un ciclo de tres días es una sola tarjeta.
    "Museo Moderno":            ("https://museomoderno.org/agenda/?jsf=jet-engine:"
                                 "aplicarbusqueda&meta=tipo-de-evento:Cine",
                                 r"jet-listing-dynamic-post-(\d+)"),
    "Archivo General de la Nación": ("https://www.argentina.gob.ar/interior/"
                                     "archivo-general-de-la-nacion/"
                                     "cine-en-el-archivo-general-de-la-nacion",
                                     "@agn"),
}
# Sin sonda a propósito: Cosmos (no responde a un GET pelado), Filo y Arthaus
# (listado renderizado por JS), Lugones / Borges (SPA o Cloudflare),
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

# Salas cuya fuente publica SÓLO la grilla del día (La Nación e IMDb). En
# cuanto la cartelera es de ayer —una corrida que cruza la medianoche
# alcanza— quedan con cero funciones futuras sin que nada esté roto. Como son
# las de más volumen, encabezaban el informe con una alarma falsa. Se les pide
# dos snapshots en cero, que ya no se explican por el vuelco de día.
#
# No alcanza con mirar el prefijo de cadena: el Cine Lorca no es cadena y sale
# de la misma fuente, y las salas de Cinemark/Hoyts sí publican con
# anticipación por su propia API.
FUENTE_SOLO_HOY = {
    "Cine Lorca", "Cinépolis Houssay", "Cinépolis Recoleta", "Showcase Belgrano",
}

# Un título que son varias películas, o una película más una actividad. El « + »
# con espacios es como el CCK une un programa doble; el resto son las actividades
# que cuelgan de la misma línea de horario. Se pide además que la función no
# tenga director, para no marcar un título que legítimamente lleve alguna de
# estas palabras.
_TITULO_COMPUESTO = re.compile(
    r"\s\+\s|\bcharlas?\s+con\b|\bconversatorio\b|\bpresentaci[óo]n\s+de\b|"
    r"\bseguida\s+de\s+(?:charla|debate)\b", re.IGNORECASE)

SEV_ERROR, SEV_WARN, SEV_INFO = "ERROR", "AVISO", "INFO"

# Cuántos días atrás sigue contando un hallazgo como "nuevo" en el informe, y
# cuánto se recuerda uno cerrado: si vuelve a aparecer en ese plazo es el
# mismo (una fuente que se cae día por medio), no una novedad.
DIAS_NUEVO = 7
DIAS_REAPARECE = 7
DIAS_MEMORIA_CERRADOS = 28


@dataclass
class Hallazgo:
    sev: str
    agente: str
    ciudad: str            # "ba", "madrid", o "" si no es de una ciudad
    cine: str              # la sala o el festival; "" en los resúmenes
    regla: str             # slug estable: con el agente, la ciudad y la sala es su identidad
    msg: str
    desde: str = ""        # cuándo apareció por primera vez (YYYY-MM-DD)
    nuevo: bool = True     # apareció en los últimos DIAS_NUEVO días
    efimero: bool = False  # no se anuncia cuando deja de salir (la web de un festival cambió)
    ejemplos: list = field(default_factory=list)

    @property
    def id(self) -> str:
        return "/".join((self.agente, self.ciudad or "-", self.regla or "-", self.cine or "-"))

    @property
    def titulo(self) -> str:
        """Una línea para acordarse de qué era cuando se resuelva."""
        texto = re.sub(r"\*\*", "", self.msg)
        corto = texto if len(texto) <= 110 else texto[:107].rsplit(" ", 1)[0] + "…"
        return f"{self.cine}: {corto}" if self.cine and not texto.startswith(self.cine) else corto


class Excepciones:
    """Lo que ya se miró y se aceptó (data/audit_excepciones.json).

    Cada entrada dice la `regla`, opcionalmente la `cine` y el dato (`valor`
    exacto o `contiene`), el `motivo` y, si es por un tiempo, `hasta`. Sin
    motivo no vale: una excepción sin explicación es un hallazgo escondido.
    Las vencidas dejan de aplicar solas y el informe las nombra.
    """

    def __init__(self, entradas: Optional[list] = None, hoy: Optional[date] = None) -> None:
        self.vigentes: list[tuple[int, dict]] = []
        self.vencidas: list[dict] = []
        self.invalidas: list[dict] = []
        self.usos: Counter = Counter()
        for i, e in enumerate(entradas or []):
            if not isinstance(e, dict) or not e.get("regla") or not e.get("motivo"):
                self.invalidas.append(e)
            elif e.get("hasta") and hoy and e["hasta"] < hoy.isoformat():
                self.vencidas.append(e)
            else:
                self.vigentes.append((i, e))

    @classmethod
    def de_archivo(cls, path: Path, hoy: date) -> "Excepciones":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls([], hoy)
        except Exception:
            exc = cls([], hoy)
            exc.invalidas.append({"motivo": f"{path.name} no es un JSON válido"})
            return exc
        return cls(data.get("excepciones", []) if isinstance(data, dict) else data, hoy)

    def cubre(self, regla: str, cine: str = "", valor: str = "") -> bool:
        for i, e in self.vigentes:
            if e["regla"] != regla:
                continue
            if e.get("cine") and e["cine"] != cine:
                continue
            if e.get("valor") and categorias.norm(e["valor"]) != categorias.norm(valor):
                continue
            if e.get("contiene") and categorias.norm(e["contiene"]) not in categorias.norm(valor):
                continue
            self.usos[i] += 1
            return True
        return False

    @property
    def sin_uso(self) -> list:
        return [e for i, e in self.vigentes if not self.usos[i]]


class Report:
    """Junta los hallazgos y arma un informe que se lee de arriba hacia abajo.

    El orden importa más que la completitud: primero el veredicto, después lo
    nuevo, después lo que sigue abierto, lo que cambió, los festivales, y
    recién al final lo que viene arrastrándose hace rato y el tablero entero.
    Un informe que empieza con una tabla de treinta filas no se lee.
    """

    def __init__(self, excepciones: Optional[Excepciones] = None) -> None:
        self.hallazgos: list[Hallazgo] = []
        self.cambios: list[str] = []               # diff contra la semana pasada
        self.resueltos: list[str] = []             # lo que estaba abierto y ya no sale
        self.contexto = ""                         # línea de estado
        self.festivales: list[str] = []            # la sección Festivales, línea por línea
        self.tableros: dict[str, list] = {}        # ciudad → filas del tablero de fuentes
        self.partes: dict[str, list] = {}          # agente → qué revisó
        self.caidos: dict[str, str] = {}           # agente → por qué no pudo terminar
        self.tabla: list[tuple] = []               # cines por debajo de lo habitual
        self.sin_novedad = 0
        self.excepciones = excepciones or Excepciones()
        self.con_memoria = False                   # ¿había un informe anterior con qué comparar?
        # A quién se le anota lo que entra: lo va cambiando el que orquesta.
        self.agente = "fuentes"
        self.ciudad = "ba"

    # ── Entrada ───────────────────────────────────────────────────────────
    def _sumar(self, sev: str, cine: str, msg: str, regla: str, **kw) -> None:
        if self.excepciones.cubre(regla, cine, msg):
            return
        self.hallazgos.append(Hallazgo(
            sev, kw.pop("agente", self.agente), kw.pop("ciudad", self.ciudad),
            cine, regla or "general", msg, **kw))

    def accionar(self, cine: str, msg: str, regla: str = "", **kw) -> None:
        self._sumar(SEV_ERROR, cine, msg, regla, **kw)

    def cronicar(self, msg: str, cine: str = "", regla: str = "", **kw) -> None:
        self._sumar(SEV_WARN, cine, msg, regla, **kw)

    def cambiar(self, msg: str) -> None:
        self.cambios.append(msg)

    def revisado(self, que: str) -> None:
        """El agente de turno anota qué miró: va al parte."""
        self.partes.setdefault(self.agente, []).append(que)

    # ── Lecturas ──────────────────────────────────────────────────────────
    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.sev == SEV_ERROR]

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.sev == SEV_WARN]

    @property
    def accion(self) -> list[tuple[str, str]]:
        return [(h.cine, h.msg) for h in self.errores]

    @property
    def cronico(self) -> list[str]:
        return [h.msg for h in self.avisos]

    @property
    def n_errors(self) -> int:
        return len(self.errores)

    @property
    def veredicto(self) -> str:
        errores = self.errores
        if not errores:
            return "✅ Todo en orden"
        lugares = {h.cine for h in errores if h.cine}
        if len(errores) == 1 and lugares:
            return f"🔴 Hay algo para mirar en {next(iter(lugares))}"
        texto = f"🔴 Hay {len(errores)} cosas para mirar"
        nuevas = sum(1 for h in errores if h.nuevo)
        if self.con_memoria and 0 < nuevas < len(errores):
            texto += f", {nuevas} nueva{'s' if nuevas != 1 else ''}"
        elif self.con_memoria and not nuevas:
            texto += ", ninguna nueva"
        return texto

    def asunto(self, hoy: date) -> str:
        return f"{self.veredicto} (cartelera al {hoy:%d/%m})"

    # ── Salida ────────────────────────────────────────────────────────────
    def _linea(self, h: Hallazgo, con_edad: bool = False) -> str:
        quien = AGENTES.get(h.agente, (h.agente,))[0].lower()
        if con_edad and h.desde:
            quien += f", desde el {_dia_mes(h.desde)}"
        return f"- **{h.cine}** ({quien}): {h.msg}" if h.cine else f"- ({quien}) {h.msg}"

    def _por_ciudad(self, hallazgos: list, linea) -> list[str]:
        """Las líneas agrupadas por ciudad; sin subtítulos si es todo de una.

        Primero lo que no es de una sala: que el scrape no corra o que un
        festival empiece en tres días sin estar cargado tiene fecha, y una
        sala con el ciclo pegado al título puede esperar al final de la lista.
        """
        grupos = [("Festivales y funcionamiento", [h for h in hallazgos if h.ciudad not in ("ba", "madrid")]),
                  ("Buenos Aires", [h for h in hallazgos if h.ciudad == "ba"]),
                  ("Madrid", [h for h in hallazgos if h.ciudad == "madrid"])]
        grupos = [(t, hs) for t, hs in grupos if hs]
        out: list[str] = []
        for titulo, hs in grupos:
            if len(grupos) > 1:
                out += [f"### {titulo}", ""]
            out += [linea(h) for h in hs]
            out.append("")
        return out

    def _parte(self) -> list[str]:
        out = ["## Parte de los agentes", "",
               "Cada uno tiene una sola cosa a cargo y entrega su parte aunque no "
               "tenga nada que decir.", "",
               "| Agente | Qué cuida | Qué revisó | Resultado |", "|---|---|---|---|"]
        for clave, (nombre, cuida) in AGENTES.items():
            if clave in self.caidos:
                resultado = f"💥 no pudo terminar: {self.caidos[clave]}"
            else:
                e = sum(1 for h in self.errores if h.agente == clave)
                a = sum(1 for h in self.avisos if h.agente == clave)
                resultado = "✅ sin novedades" if not (e or a) else " y ".join(
                    x for x in (f"🔴 {e} para mirar" if e else "",
                                f"🟡 {a} pendiente{'s' if a != 1 else ''}" if a else "") if x)
            reviso = "; ".join(self.partes.get(clave, [])) or "no llegó a revisar nada"
            out.append(f"| {nombre} | {cuida} | {reviso} | {resultado} |")
        out.append("")
        return out

    def _tablero(self) -> list[str]:
        if not any(self.tableros.values()):
            return []
        out = ["## Tablero de fuentes", "",
               "Cómo viene cada sala: funciones publicadas, hasta qué día llega su "
               "programación, cuántas tenía hace una semana, cuántos de los últimos días "
               "contestó su fuente, y una barrita por día de las últimas cuatro semanas.", ""]
        con_ciudades = sum(1 for filas in self.tableros.values() if filas) > 1
        peor: dict = {}
        for h in self.hallazgos:
            if h.agente == "fuentes" and h.cine:
                k = (h.ciudad, h.cine)
                peor[k] = SEV_ERROR if SEV_ERROR in (h.sev, peor.get(k)) else SEV_WARN
        for ciudad, filas in self.tableros.items():
            if not filas:
                continue
            if con_ciudades:
                out += [f"### {CIUDADES[ciudad][0]}", ""]
            out += ["| Sala | Func. | Títulos | Hasta | Hace 7 días | Fuente | Cuatro semanas |",
                    "|---|---:|---:|---|---:|---|---|"]
            apagadas = []
            for r in filas:
                marca = {SEV_ERROR: "🔴", SEV_WARN: "🟡"}.get(peor.get((ciudad, r["sala"])), "")
                if not r["n"] and not marca:
                    if r["ultimo"]:
                        apagadas.append(f"{r['sala']} (desde el {_dia_mes(r['ultimo'])})")
                    continue
                marca = marca or "🟢"
                hace7 = "" if r["hace7"] is None else str(r["hace7"])
                out.append(f"| {marca} {r['sala']} | {r['n']} | {r['titulos']} | "
                           f"{_dia_mes(r['hasta']) if r['hasta'] else ''} | {hace7} | "
                           f"{_fuente_texto(r)} | `{chispa(r['serie'])}` |")
            out.append("")
            if apagadas:
                out += ["Sin funciones y sin nada que marcar (salas de festival o que programan "
                        "cada tanto): " + ", ".join(apagadas) + ".", ""]
        return out

    def render(self, hoy: date) -> str:
        out = [f"# Auditoría de la cartelera, {_fecha_larga(hoy)}", "",
               f"## {self.veredicto}", "", self.contexto, ""]

        errores = self.errores
        nuevos = [h for h in errores if h.nuevo]
        viejos = [h for h in errores if not h.nuevo]
        if errores and self.con_memoria and viejos:
            if nuevos:
                out += ["## Nuevo esta semana", ""] + self._por_ciudad(nuevos, self._linea)
            out += ["## Sigue abierto", "",
                    "Ya salió en un informe anterior y todavía no se arregló.", ""]
            out += self._por_ciudad(viejos, lambda h: self._linea(h, con_edad=True))
        elif errores:
            out += ["## Para mirar esta semana", ""] + self._por_ciudad(errores, self._linea)

        out += ["## Qué cambió desde la semana pasada", ""]
        if self.cambios or self.resueltos:
            out += [f"- {c}" for c in self.cambios]
            out += [f"- Se resolvió: {r}" for r in self.resueltos]
        else:
            out.append("Nada raro: ningún cine se cayó ni pegó un salto respecto de "
                       "la semana pasada.")
        out.append("")

        if self.festivales:
            out += ["## Festivales", ""] + [f"- {l}" for l in self.festivales] + [""]

        out += self._parte()

        if self.avisos:
            out += ["## Pendientes de siempre", "",
                    "Cosas que no rompen la web pero degradan la ficha. "
                    "Están acá para que no se olviden, no para arreglarlas hoy.", ""]
            out += self._por_ciudad(self.avisos, lambda h: f"- {h.msg}")

        out += self._tablero()

        exc = self.excepciones
        notas = []
        if exc.vigentes:
            usadas = len(exc.vigentes) - len(exc.sin_uso)
            notas.append(f"{_n(len(exc.vigentes), 'excepción vigente', 'excepciones vigentes')} en "
                         f"`data/audit_excepciones.json`, {usadas} en uso esta semana")
        if exc.vencidas:
            notas.append(f"{_n(len(exc.vencidas), 'excepción vencida', 'excepciones vencidas')} que ya no aplican y se pueden borrar")
        if exc.invalidas:
            notas.append(f"{_n(len(exc.invalidas), 'excepción mal escrita', 'excepciones mal escritas')} (les falta la regla o el motivo) "
                         f"que no se están aplicando")
        out += ["---", ""]
        if notas:
            out += [". ".join(n[0].upper() + n[1:] for n in notas) + ".", ""]
        out += ["Generado por `scripts/audit.py`. Para correrlo a mano: "
                "`cd ~/cines && python3 scripts/audit.py`. Para que los agentes "
                "revisen y arreglen lo que encontró: `/auditoria` en Claude."]
        return "\n".join(out)

    def alerta(self, nuevos: list, hoy: date) -> tuple[str, str]:
        """(asunto, markdown) del aviso del centinela: sólo lo que apareció hoy."""
        if len(nuevos) == 1 and nuevos[0].cine:
            asunto = f"🔴 Nuevo en la cartelera: {nuevos[0].cine}"
        else:
            asunto = f"🔴 {len(nuevos)} cosas nuevas en la cartelera"
        out = [f"# Centinela de la cartelera, {_fecha_larga(hoy)}", "",
               f"## {asunto}", "",
               "Esto no estaba ayer. El informe completo llega el lunes.", ""]
        out += self._por_ciudad(nuevos, self._linea)
        out += ["---", "", "Generado por `scripts/audit.py --centinela`. Para que los agentes "
                "lo revisen ahora: `/auditoria` en Claude."]
        return asunto, "\n".join(out)


_MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fecha_larga(d: date) -> str:
    return f"{_DIAS_LARGO[d.weekday()]} {d.day} de {_MESES_LARGO[d.month - 1]}"


def _dia_mes(iso: str) -> str:
    """"2026-11-05" → "5/11"."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day}/{d.month}"


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _n(n: int, uno: str, muchos: str) -> str:
    """"1 función" / "14 funciones": el número con su sustantivo."""
    return f"{_miles(n)} {uno if n == 1 else muchos}"


def _fuente_texto(r: dict) -> str:
    """La columna Fuente del tablero, en pocas palabras."""
    if r["n"] and r["a_mano"] >= r["n"]:
        return "a mano"
    if r["n"] and r["scrapeadas"] == 0:
        dias = r["racha_caida"]
        return f"caída hace {dias} día{'s' if dias != 1 else ''}" if dias else "caída hoy"
    if r["viva"]:
        return f"{r['viva'][0]} de {r['viva'][1]} días"
    return ""


# Conversor markdown → HTML para el subconjunto que usa el informe (títulos,
# tabla, viñetas, negrita, code). Es para el mail: el cuerpo tiene que verse
# bien en un cliente de correo, y no vale la pena meter una dependencia ni
# reescribir el render entero — el markdown sigue siendo la fuente única.
def md_a_html(md: str) -> str:
    def inline(t: str) -> str:
        t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        return re.sub(r"`(.+?)`", r'<code style="font-family:Menlo,Consolas,monospace;'
                                   r'font-size:12px">\1</code>', t)

    out: list[str] = []
    en_lista = en_tabla = False
    for linea in md.splitlines():
        l = linea.rstrip()
        es_fila = l.startswith("|")
        if en_lista and not l.startswith("- "):
            out.append("</ul>"); en_lista = False
        if en_tabla and not es_fila:
            out.append("</table>"); en_tabla = False
        if not l:
            continue
        if l == "---":
            out.append('<hr style="border:0;border-top:1px solid #ddd;margin:22px 0 10px">')
        elif l.startswith("### "):
            out.append(f'<h4 style="margin:14px 0 6px;font-size:14px;color:#555">'
                       f'{inline(l[4:])}</h4>')
        elif l.startswith("## "):
            texto = l[3:]
            color = "#d93025" if texto.startswith("🔴") else "#1a1a1a"
            out.append(f'<h3 style="color:{color};margin:22px 0 8px;font-size:16px">'
                       f'{inline(texto)}</h3>')
        elif l.startswith("# "):
            out.append(f'<h2 style="margin:0 0 6px;font-size:20px">{inline(l[2:])}</h2>')
        elif es_fila:
            celdas = [c.strip() for c in l.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                continue          # separador de encabezado
            # El estilo va en la tabla y en la fila, no en cada celda: el
            # tablero tiene más de sesenta filas, y Gmail corta los mails que
            # pasan los 102 KB ("mensaje recortado").
            if not en_tabla:
                out.append('<table cellpadding="3" cellspacing="0" style="border-collapse:'
                           'collapse;font-size:13px;margin:8px 0;text-align:left">')
                en_tabla = True
                out.append('<tr style="border-bottom:1px solid #ccc">' + "".join(
                    f"<th>{inline(c)}</th>" for c in celdas) + "</tr>")
                continue
            out.append('<tr valign="top" style="border-bottom:1px solid #eee">' + "".join(
                f"<td>{inline(c)}</td>" for c in celdas) + "</tr>")
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
            "Helvetica,Arial,sans-serif;max-width:760px;color:#1a1a1a;"
            'line-height:1.5">' + "\n".join(out) + "</div>")


# --------------------------------------------------------------------------
# Carga de datos
# --------------------------------------------------------------------------

def load_cartelera(ciudad: str = "ba") -> tuple[dict, list[dict]]:
    path = ROOT / CIUDADES[ciudad][1]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, data.get("screenings", [])


def git_snapshots(n_days: int = 14, path: str = "data/cartelera.json") -> dict[str, Counter]:
    """Último commit de cada uno de los últimos n_days días que tocó la
    cartelera → Counter de funciones futuras por cine en ese momento.

    Es la línea de base: un cine que venía trayendo 20 funciones por día y hoy
    trae 0 está roto, aunque el scraper no haya tirado ningún error. Devuelve
    {} si el repo es un clone shallow (CI sin fetch-depth: 0) o no hay git.
    """
    hist = Historia.de_git(ROOT, path, dias=n_days, detalle=0)
    return {d: hist.funciones[d] for d in hist.dias}


def leer_padron(root: Path = ROOT) -> tuple[dict, list, set]:
    """Las salas que la web conoce, según index.html:
    ({sala: "ba" | "madrid"}, prefijos de las cadenas, salas con dirección).

    Es el padrón contra el que se mide todo lo demás: una sala que está acá y
    no tiene funciones tiene que aparecer en el informe aunque lleve meses
    así, y una función en una sala que no está acá no tiene chip ni dirección.
    """
    try:
        html = (root / "index.html").read_text(encoding="utf-8")
    except Exception:
        return {}, [], set()
    salas: dict = {}
    for m in re.finditer(r'<button class="([^"]*)" data-cine="([^"]+)"([^>]*)>', html):
        clases, cine, resto = m.groups()
        if "filter-btn" not in clases or "commercial-chip" in clases:
            continue
        if cine == "all" or "$" in cine:
            continue
        salas[cine] = "madrid" if 'data-ciudad="madrid"' in resto else "ba"
    pref = re.search(r"const COMMERCIAL_PREFIXES = \[([^\]]*)\]", html)
    prefijos = re.findall(r"'([^']+)'", pref.group(1)) if pref else []
    dirs = re.search(r"const CINE_ADDRESSES = \{(.*?)\n\};", html, re.DOTALL)
    direcciones = set(re.findall(r"^\s*'([^']+)'\s*:", dirs.group(1), re.MULTILINE)) if dirs else set()
    return salas, prefijos, direcciones


def cargar_manual(root: Path = ROOT) -> tuple[dict, set]:
    """(manual_screenings.json, claves de las funciones cargadas a mano)."""
    try:
        manual = json.loads((root / "data" / "manual_screenings.json").read_text(encoding="utf-8"))
    except Exception:
        manual = {}
    claves = {categorias.clave_a_mano(s) for s in manual.get("screenings", [])}
    try:
        cb = json.loads((root / "data" / "cb_manual.json").read_text(encoding="utf-8"))
        claves |= {categorias.clave_a_mano(dict(s, cine="Casa del Bicentenario"))
                   for s in cb.get("screenings", [])}
    except Exception:
        pass
    return manual, claves


# --------------------------------------------------------------------------
# La memoria: qué estaba abierto y desde cuándo (data/audit.json → "estado")
# --------------------------------------------------------------------------

def cargar_estado(path: Path = ESTADO) -> Optional[dict]:
    """El estado que dejó la corrida anterior, o None si no hay."""
    try:
        estado = json.loads(path.read_text(encoding="utf-8")).get("estado")
    except Exception:
        return None
    if not isinstance(estado, dict) or "abiertos" not in estado:
        return None
    estado.setdefault("cerrados", {})
    return estado


def fechar(rep: Report, estado: Optional[dict], hoy: date) -> tuple[dict, list[Hallazgo]]:
    """Le pone a cada hallazgo desde cuándo está abierto, anota en el informe
    lo que se resolvió, y devuelve (estado nuevo, ERRORes que no estaban).

    Un hallazgo es el mismo de una corrida a la otra si coinciden agente,
    ciudad, regla y sala. Si se cerró hace poco y vuelve, sigue siendo el
    mismo: una fuente que se cae día por medio no es una novedad cada vez.
    """
    hoy_s = hoy.isoformat()
    previo = estado or {"abiertos": {}, "cerrados": {}}
    abiertos, cerrados = previo["abiertos"], dict(previo.get("cerrados", {}))
    rep.con_memoria = estado is not None
    limite_nuevo = (hoy - timedelta(days=DIAS_NUEVO)).isoformat()
    limite_reaparece = (hoy - timedelta(days=DIAS_REAPARECE)).isoformat()

    estrenan: list[Hallazgo] = []
    nuevo_abiertos: dict = {}
    for h in rep.hallazgos:
        antes = abiertos.get(h.id)
        reciente = cerrados.get(h.id)
        if antes:
            h.desde = antes.get("desde") or hoy_s
            era_error = antes.get("sev") == SEV_ERROR
        elif reciente and reciente.get("cerrado", "") >= limite_reaparece:
            h.desde = reciente.get("desde") or hoy_s
            era_error = reciente.get("sev") == SEV_ERROR
            cerrados.pop(h.id, None)
        else:
            h.desde = hoy_s
            era_error = False
            cerrados.pop(h.id, None)
        h.nuevo = h.desde > limite_nuevo or estado is None
        if h.sev == SEV_ERROR and not era_error:
            estrenan.append(h)
        # El título se guarda como estaba el día que apareció: los mensajes
        # cuentan días ("lleva 30 días"), y si se reescribieran en cada pasada
        # el archivo cambiaría todos los días sin que haya pasado nada.
        mismo = antes and antes.get("sev") == h.sev and antes.get("titulo")
        nuevo_abiertos[h.id] = {"desde": h.desde, "sev": h.sev,
                                "titulo": antes["titulo"] if mismo else h.titulo,
                                "efimero": h.efimero}

    for hid, antes in abiertos.items():
        if hid not in nuevo_abiertos:
            cerrados[hid] = dict(antes, cerrado=hoy_s)
    limite_memoria = (hoy - timedelta(days=DIAS_MEMORIA_CERRADOS)).isoformat()
    cerrados = {k: v for k, v in sorted(cerrados.items())
                if v.get("cerrado", "") >= limite_memoria}
    nuevo_abiertos = dict(sorted(nuevo_abiertos.items()))

    # Lo que se cerró esta semana (hoy, o en una pasada del centinela).
    for hid, c in sorted(cerrados.items(), key=lambda kv: kv[1].get("cerrado", "")):
        if c.get("cerrado", "") > limite_nuevo and not c.get("efimero") and c.get("sev") == SEV_ERROR:
            rep.resueltos.append(f"{c.get('titulo', hid)} (estaba desde el {_dia_mes(c.get('desde', ''))})")
    return {"abiertos": nuevo_abiertos, "cerrados": cerrados}, estrenan


# --------------------------------------------------------------------------
# Sondas en vivo
# --------------------------------------------------------------------------

# Una sonda que no pudo medir no dice lo mismo según por qué falló, y la
# diferencia decide a dónde mandar al que lee el informe: si la fuente nos
# cerró la puerta (403 de Cloudflare, 401, 429) el scraper puede estar
# perfecto y no hay parser que arreglar; si el que falló fuimos nosotros
# (timeout, DNS) no se puede concluir nada. El prefijo marca cuál es cuál.
_RECHAZO = "rechazo:"


def probe(cine: str, url: str, pattern: str) -> tuple[str, int | None, str]:
    """(cine, cantidad de ítems publicados, detalle). None = no se pudo medir."""
    body = None
    for intento in (1, 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            # 401/403/429 son la fuente diciendo "vos no": el mismo bloqueo que se
            # come el scraper. 5xx es la fuente caída, que tampoco es culpa nuestra.
            marca = _RECHAZO if e.code in (401, 403, 405, 406, 429) or e.code >= 500 else ""
            return cine, None, f"{marca}HTTP {e.code}"
        except Exception as e:
            # Un timeout o un corte de red se reintenta una vez: con el
            # centinela corriendo todos los días, una sonda que no contesta
            # por un tropiezo cambia lo que el informe dice de esa sala.
            if intento == 2:
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

    if pattern == "@cea":
        # Cada función del CEA es una card con data-field="titulo". Se
        # descuentan las que cuelgan de un bloque .hidden-temp: la home
        # arrastra secciones viejas con display:none —el cronograma de julio,
        # sin ir más lejos— y contarlas daría funciones que la página no
        # muestra. Es la misma regla que aplica el scraper.
        limpio = re.sub(r'<[^>]*class="[^"]*hidden-temp[^"]*"[^>]*>.*?</div>', " ",
                        body, flags=re.DOTALL | re.IGNORECASE)
        n = len(re.findall(r'data-field="titulo"', limpio)) or len(re.findall(r'class="[^"]*film-col', limpio))
        return cine, n, "funciones anunciadas en la home"

    if pattern == "@farus":
        # Los eventos de Farus por venir, del catálogo que la búsqueda de
        # Central Ticket trae embebido: {id:"11190",
        # eventURL:"2211CineclubFarus", title:"Cineclub Farus", …,
        # dateEndKey:"2026-11-22"}. Antes se contaban los links
        # /event/<slug> que dijeran "farus" en minúsculas, y los de noviembre
        # de 2026 vienen con mayúsculas: la sonda contó 0, el informe leyó "no
        # programó" y Farus estuvo dos semanas fuera de la web sin que ningún
        # informe lo nombrara. Si la página deja de traer el catálogo, la
        # sonda dice que no pudo medir en vez de contestar 0.
        hoy = date.today().isoformat()
        marcas = list(re.finditer(r'\{id:"(\d+)",', body))
        eventos, con_fecha = set(), 0
        for i, m in enumerate(marcas):
            fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(body)
            trozo = body[m.end():min(fin, m.end() + 3000)]
            fecha = (re.search(r'dateEndKey:"(\d{4}-\d{2}-\d{2})"', trozo)
                     or re.search(r'dateStartKey:"(\d{4}-\d{2}-\d{2})"', trozo))
            if not fecha:
                continue
            con_fecha += 1
            if fecha.group(1) >= hoy and re.search(r"farus", trozo, re.IGNORECASE):
                eventos.add(m.group(1))
        if not con_fecha:
            return cine, None, "la búsqueda de Central Ticket cambió de formato"
        return cine, len(eventos), "eventos por venir en Central Ticket"

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

# Workflows que, si su última corrida falló, hay que mirar ya: de ellos
# depende que la web y las stories salgan.
WORKFLOWS_CLAVE = ("Scrape cartelera", "Scrape cartelera (sin postear a IG)",
                   "Post to Instagram", "Renovar token de Instagram")


def _repo_github() -> str:
    """"dueño/repo", del entorno de Actions o del remoto de git."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        return repo
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:
        return ""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def corridas_de_actions(desde: date) -> Optional[list]:
    """Las corridas de los workflows desde `desde`, o None si no se pudo
    preguntar. La API es pública; con GITHUB_TOKEN no se queda sin cupo."""
    repo = _repo_github()
    if not repo:
        return None
    url = (f"https://api.github.com/repos/{repo}/actions/runs"
           f"?per_page=100&created=%3E%3D{desde.isoformat()}")
    headers = {"User-Agent": "auditoria-cartelera", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.loads(r.read().decode("utf-8")).get("workflow_runs", [])
    except Exception:
        return None


def check_corridas(rep: Report, corridas: Optional[list]) -> None:
    """Los workflows de la semana: cuál viene fallando.

    La cartelera puede estar fresca y las stories posteadas con un workflow
    que falla la mitad de las veces y se salva en el reintento. Y el que
    renueva el token de Instagram falla en silencio hasta el día en que el
    token vence y las stories dejan de salir.
    """
    if corridas is None:
        rep.revisado("las corridas de Actions no se pudieron consultar")
        return
    por_wf: dict[str, list] = defaultdict(list)
    for r in corridas:
        # Un workflow que ya se sacó del repo no tiene nada que arreglar: el
        # de GitHub Pages falló en cada corrida hasta que se borró el 12/11.
        archivo = r.get("path") or ""
        if archivo and not (ROOT / archivo).exists():
            continue
        if r.get("status") == "completed":
            por_wf[r.get("name", "")].append(r)       # la más nueva primero
    total = sum(len(v) for v in por_wf.values())
    rep.revisado(f"{total} corridas de {len(por_wf)} workflows en la semana")
    for nombre, rs in sorted(por_wf.items()):
        fallas = [r for r in rs if r.get("conclusion") in ("failure", "timed_out", "startup_failure")]
        if not fallas:
            continue
        cuando = _dia_mes((fallas[0].get("created_at") or "")[:10])
        ultima_fallo = rs[0] in fallas
        if ultima_fallo and nombre in WORKFLOWS_CLAVE:
            rep.accionar(nombre, f"su última corrida falló (el {cuando}); en la semana "
                                 f"fallaron {len(fallas)} de {len(rs)}. Mirala en Actions.",
                         regla="workflow-fallando", ciudad="")
        else:
            rep.cronicar(f"**{nombre}** (workflow): fallaron {len(fallas)} de {len(rs)} corridas "
                         f"de la semana, la última el {cuando}"
                         + ("." if not ultima_fallo else ", y es la más reciente."),
                         cine=nombre, regla="workflow-fallas", ciudad="")


def check_stories(rep: Report, today: date, dias: int = 7) -> None:
    """Que las stories de Instagram hayan salido cada día.

    post_to_instagram.py deja posts/<fecha>/.posteado-… cuando publica. El día
    de hoy no cuenta: a la hora de la auditoría puede no haber salido todavía.
    """
    carpeta = ROOT / "posts"
    if not carpeta.is_dir():
        return
    faltan = []
    for i in range(1, dias + 1):
        d = today - timedelta(days=i)
        dia = carpeta / d.isoformat()
        if not dia.is_dir() or not any(p.name.startswith(".posteado") for p in dia.iterdir()):
            faltan.append(d)
    rep.revisado(f"las stories de {dias} días")
    if faltan:
        cuales = ", ".join(_dia_mes(d.isoformat()) for d in sorted(faltan))
        rep.accionar("Instagram", f"las stories de {_n(len(faltan), 'día', 'días')} de la semana "
                                  f"no figuran como posteadas ({cuales}). Mirá las corridas de "
                                  f"`post-ig.yml` de esos días.",
                     regla="stories", ciudad="")


def check_frescura(rep: Report, datos: dict, today: date, medir_edad: bool = True) -> float:
    """`datos`: {ciudad: (meta, funciones)}. Devuelve las horas que tienen los
    datos de Buenos Aires (inf si no se sabe)."""
    hoy = today.isoformat()
    partes = []
    for ciudad, (meta, screenings) in datos.items():
        fut = [s for s in screenings if s.get("fecha", "") >= hoy]
        salas = len({s["cine"] for s in fut})
        partes.append(f"{CIUDADES[ciudad][0]}: {salas} salas y {_miles(len(fut))} funciones")
    resumen = ". ".join(partes) + "."
    rep.revisado(f"{len(datos)} cartelera{'s' if len(datos) != 1 else ''}")

    horas = float("inf")
    for ciudad, (meta, _) in datos.items():
        raw = meta.get("updated", "")
        try:
            updated = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            rep.accionar(CIUDADES[ciudad][1], f"el campo `updated` quedó ilegible: {raw!r}",
                         regla="updated-ilegible", ciudad="")
            continue
        h = (datetime.now() - updated).total_seconds() / 3600
        if ciudad == "ba" or horas == float("inf"):
            horas = h
        # El scrape corre a diario: más de 36 h es una corrida perdida.
        if h > 36 and ciudad == "ba" and medir_edad:
            rep.accionar("El scrape diario",
                         f"los datos son de hace {h:.0f} h: el workflow `scrape.yml` no está "
                         f"commiteando. Mirá la última corrida en Actions.",
                         regla="scrape-atrasado", ciudad="")
    rep.contexto = (f"Datos de hace {horas:.0f} h. {resumen}" if horas != float("inf")
                    else resumen)
    return horas


# Cuándo una sala en cero es para avisar (ver check_cobertura).
ALTA_FRECUENCIA = 5      # funciones/día a partir de las cuales un cero es raro
RACHA_CHICA = 3          # días en cero que hacen mirar hasta a una sala chica
RACHA_LARGA = 7          # días en cero que se nombran aunque la sonda diga 0
RACHA_DE_SEMANAS = 21    # días en cero que ya son para mirar, diga lo que diga la sonda
# Con el historial largo: qué hace falta para decir que una sala "programaba
# seguido" antes de apagarse. Una que aparece ocho días por un festival no.
VIDA_MIN = 21            # días entre su primera y su última función
PRESENCIA_MIN = 0.5      # proporción de esos días en que tuvo funciones
# Las salas que se bajan por el proxy pago: run.py las scrapea sólo en el pase
# de la madrugada (el de la tarde va con --sin-proxy).
SOLO_DE_MADRUGADA = {"CCK", "Centro Cultural Borges"}
# Una sala en cero es UN hallazgo, lo explique quien lo explique (la sonda
# que encontró programación, la que no encontró nada, el 403, el scraper). Si
# cada explicación tuviera su regla, el día que una sonda no contesta el mismo
# cero cambiaría de nombre y el centinela lo avisaría como si fuera nuevo.
EN_CERO = "sin-funciones"


def _es_de_festival(ciclo: str, claves_festival: list) -> bool:
    base = categorias.norm(categorias.ciclo_base(ciclo))
    if not base:
        return False
    return "festival" in base.split() or any(f" {k} " in f" {base} " for k in claves_festival)


def _sala_de_festival(cine: str, largo: Optional[Historia], claves_festival: list) -> bool:
    """¿Lo último que tuvo esta sala fue todo de un festival? Entonces que
    esté en cero es que el festival terminó, no que se cayó: el Marechal trajo
    51 funciones por día durante el FESTIHUR y al terminar salía como caído."""
    if not largo:
        return False
    ult = largo.ultimo_con_funciones(cine)
    if not ult:
        return False
    filas = [s for s in largo.filas(ult) if s.get("cine") == cine and s.get("fecha", "") >= ult]
    return bool(filas) and all(_es_de_festival(s.get("ciclo") or "", claves_festival) for s in filas)


def check_cobertura(rep: Report, screenings: list[dict], today: date,
                    snaps: dict[str, Counter], probes: dict,
                    fuentes: dict | None = None, *, largo: Optional[Historia] = None,
                    padron: Optional[set] = None, sondas: Optional[dict] = None,
                    claves_festival: Optional[list] = None) -> None:
    """`largo`: el historial de meses (audit_fuentes.Historia), para las salas
    que llevan caídas más que la ventana de `snaps`. `padron`: las salas que
    la web conoce para esta ciudad. `sondas`: las que tienen sonda en esta
    ciudad (por defecto, PROBES)."""
    fuentes = fuentes or {}
    sondas = PROBES if sondas is None else sondas
    hoy = today.isoformat()
    fut = defaultdict(list)
    for s in screenings:
        if s.get("fecha", "") >= hoy:
            fut[s["cine"]].append(s)

    # Universo de cines: los de hoy + los del histórico + los que tienen sonda
    # + los que la web conoce. Un cine que desapareció del todo es el caso más
    # grave, y sin esta unión pasaría inadvertido; incluir los sondeados y el
    # padrón cubre además a los que ya llevan más días caídos que la ventana
    # del histórico.
    universo = (set(fut) | {c for snap in snaps.values() for c in snap} | set(sondas)
                | set(padron or ()))
    if largo:
        universo |= largo.salas()
    baseline = {
        c: median([snap.get(c, 0) for snap in snaps.values()])
        for c in universo
    } if snaps else {}

    # La mediana contesta "cuánto trae habitualmente", que es lo que hay que
    # decir en el mensaje, pero no sirve para decidir SI avisar: en cuanto un
    # cine lleva más de media ventana caído, su propia mediana es 0 y el cine
    # desaparece del informe. Es el peor modo de falla posible para esto —
    # cuanto más tiempo lleva roto, más silencioso—, y ya pasó: el Museo del
    # Cine llevaba ocho días en cero sin que ningún informe lo nombrara.
    # Así que decidir si avisar y describir cuánto traía pasan a ser dos
    # cuentas distintas, y ninguna de las dos puede salir de la mediana cruda.
    #
    # Cuánto traía: la mediana de los días en que trajo ALGO. El máximo sería
    # lo obvio, pero un solo día de datos basura lo secuestra —Cosmos llegó a
    # publicar 843 funciones el día que una película se llevaba los horarios de
    # todas las demás— y un informe que dice "traía hasta 843 por día" no se
    # cree. Salteando los ceros, la mediana describe el cine cuando anda.
    #
    # Cuándo avisar: lo que separa un cine roto de uno que no programó es el
    # volumen que mueve cuando anda, no la forma del hueco. Una sala que trae
    # quince funciones por día no se queda en cero porque sí; el CEA, que trae
    # tres, entra y sale del cero todo el tiempo y avisar por cada hueco
    # entrena a ignorar el informe.
    #
    # Se probó calibrar la racha contra la peor racha previa de ese mismo cine
    # y sale mal justo en el caso que importa: un cine que se rompió, se
    # arregló y se volvió a romper lleva su propia caída anterior en la
    # ventana, así que "oscila" y el aviso se degrada. Le pasó al CCK.
    dias = sorted(snaps, reverse=True)
    habitual, racha_cero = {}, {}
    for c in universo:
        vals = [snaps[d].get(c, 0) for d in dias]
        con_funciones = [v for v in vals if v]
        habitual[c] = median(con_funciones) if con_funciones else 0
        n = 0
        for v in vals:
            if v:
                break
            n += 1
        racha_cero[c] = n

    flojos = []
    for cine in sorted(universo, key=lambda c: (-len(fut.get(c, [])), c)):
        ss = fut.get(cine, [])
        n, titulos = len(ss), len({s.get("title_es", "") for s in ss})
        base = baseline.get(cine)
        probe_n, probe_detail = probes.get(cine, (None, ""))

        es_comercial = cine.startswith(COMMERCIAL_PREFIXES)
        rancio = False

        # Un cine puede publicar funciones y tener la fuente caída igual: el
        # Borges vive del caché de la última corrida buena y la Casa del
        # Bicentenario de data/cb_manual.json. La grilla se ve llena y el
        # conteo no baja, así que ninguno de los chequeos de acá lo agarraba —
        # el Borges estuvo cuatro días así sin figurar en ningún informe. Es
        # peor que un cero: un cero se ve, esto no, y mientras tanto se publica
        # programación que nadie confirmó.
        proc = fuentes.get(cine) or {}
        if n and proc.get("publicadas") and not proc.get("scrapeadas"):
            # Cuántos días lleva sin que NINGUNA corrida le saque algo. Mirar
            # sólo la última engaña con el CCK y el Borges: el pase de la
            # tarde los saltea a propósito (--sin-proxy), así que si la
            # auditoría corre antes que el scrape de la mañana los ve en cero
            # sin que nadie los haya ido a buscar. Para esos dos hace falta
            # que ayer tampoco hayan contestado.
            racha_caida = largo.racha_caida(cine) if largo else 0
            salteada = bool(largo) and cine in SOLO_DE_MADRUGADA and racha_caida < 2
            motivo = (proc.get("fuente_caida") or (largo.ultimo_motivo(cine) if largo else "")
                      or "la fuente no contestó")
            cuanto = (f"su fuente no contesta hace {racha_caida} días" if racha_caida >= 2
                      else "no scrapeó ninguna en la última corrida")
            if not salteada:
                rep.accionar(cine, f"publica {_n(n, 'función', 'funciones')} pero {cuanto}: "
                                   f"{motivo}. Lo que se ve es lo último bueno, y se vacía "
                                   f"solo a medida que pasan las fechas.", regla="de-cache")
        elif n and proc.get("scrapeadas") and proc.get("fuente_caida"):
            # Scrapeó, pero el scraper sabe que algo le faltó: un evento de
            # Farus que no dice qué películas da, o el Cosmos viviendo de
            # Instagram con su web caída. La grilla tiene algo, así que no grita.
            rep.cronicar(f"**{cine}** publica {_n(n, 'función', 'funciones')}, pero su "
                         f"scraper avisa: {proc['fuente_caida']}.", cine=cine, regla="scraper-avisa")

        if n == 0:
            racha, hab = racha_cero.get(cine, 0), habitual.get(cine, 0)
            if _sala_de_festival(cine, largo, claves_festival or []):
                continue
            if largo and not hab:
                # Lleva en cero más que la ventana corta: ahí la mediana es 0,
                # "no hay con qué comparar" y la sala se caía del informe
                # justo cuando más tiempo llevaba rota. El CEA dejó de traer
                # funciones el 17/10/2026, después de tres meses programando
                # todas las semanas, y un mes más tarde nadie lo había visto.
                # Con el historial largo se sabe desde cuándo y cuánto traía;
                # sólo cuenta si la sala programaba seguido antes de apagarse.
                ult = largo.ultimo_con_funciones(cine)
                if (ult and largo.dias_de_vida(cine) >= VIDA_MIN
                        and largo.presencia(cine) >= PRESENCIA_MIN):
                    racha, hab = dias_entre(ult, hoy), largo.habitual(cine)
            desde = (f"lleva {racha} día{'s' if racha != 1 else ''} sin ninguna "
                     f"función" if racha else "no tiene ninguna función")
            venia = f" (traía ~{hab:.0f} por día)" if hab else ""

            if probe_detail.startswith(_RECHAZO):
                # La fuente nos rechaza a nosotros igual que rechaza al
                # scraper. Decir "revisá su scraper" acá manda a reescribir un
                # parser que puede estar intacto: lo que falta es poder entrar
                # (proxy residencial vivo, o una IP que el sitio acepte).
                rep.accionar(cine, f"{desde}{venia}, y la fuente tampoco nos deja "
                                   f"sondearla ({probe_detail[len(_RECHAZO):]}). "
                                   f"No es el parser: es acceso al sitio. Revisá "
                                   f"que el proxy de scraping siga vivo.", regla=EN_CERO)
            elif probe_n:
                rep.accionar(cine, f"{desde}{venia}, pero la fuente publica "
                                   f"{probe_n} {probe_detail}. El scraper se rompió.",
                             regla=EN_CERO)
            elif proc.get("fuente_caida"):
                # El scraper mismo dice por qué no trajo nada. Antes esto se
                # perdía si la sonda medía 0 o el cine traía poco.
                rep.accionar(cine, f"{desde}{venia}, y su scraper avisa: "
                                   f"{proc['fuente_caida']}.", regla=EN_CERO)
            elif probe_n == 0:
                # Medimos la fuente y no publica nada: el cine no programó. Es
                # la realidad, no un hallazgo… salvo que la sonda esté ciega.
                # La de Farus contó 0 del 29/10 al 15/11/2026 porque cambió el
                # formato de los links, y el informe leyó "no programó" dos
                # semanas seguidas. Con una racha larga en un cine que venía
                # programando se nombra igual, sin gritar.
                #
                # Y si ya son semanas, se grita: una sala que programaba todas
                # las semanas no pasa un mes sin nada porque sí. El CEA lleva
                # así desde el 17/10/2026. Si de verdad cerró, se anota en
                # data/audit_excepciones.json y deja de salir.
                if hab and racha >= RACHA_DE_SEMANAS:
                    rep.accionar(cine, f"{desde}{venia}, y su sonda tampoco ve nada "
                                       f"publicado. Es mucho para una sala que programaba "
                                       f"seguido: hay que abrir su web y ver si cambió dónde "
                                       f"publica o si dejó de programar.", regla=EN_CERO)
                elif hab and racha >= RACHA_LARGA:
                    rep.cronicar(f"**{cine}** {desde}{venia} y su sonda tampoco "
                                 f"ve nada publicado. Si el cine sigue "
                                 f"programando, cambió dónde publica: hay que "
                                 f"mirar la sonda y el scraper.", cine=cine, regla=EN_CERO)
            elif not hab:
                # Nunca trajo nada en la ventana: no hay con qué comparar.
                pass
            elif cine in FUENTE_SOLO_HOY and racha < 2:
                # Ver FUENTE_SOLO_HOY: un cero de un día acá es el vuelco de
                # fecha, no una caída.
                pass
            elif hab >= ALTA_FRECUENCIA or racha >= RACHA_CHICA:
                rep.accionar(cine, f"{desde}{venia}. Revisá su scraper.", regla=EN_CERO)
            else:
                # Está en cero, pero dentro de lo que este cine hace normalmente.
                # Va al informe igual —en cero está—, sin gritar.
                rep.cronicar(f"**{cine}** {desde}{venia}; entra y sale del cero "
                             f"seguido, puede que no haya programado.", cine=cine, regla=EN_CERO)
            continue

        if es_comercial and titulos < COMMERCIAL_MIN_TITLES:
            rancio = True
            rep.accionar(cine, f"sólo {titulos} película(s) distinta(s) en {n} "
                               f"funciones. Una sala de cadena nunca tiene tan "
                               f"poco: se está publicando data vieja.", regla="rancio")

        # Caída brusca contra su propio histórico. No aplica a las cadenas: La
        # Nación publica sólo el día de hoy para las que no son del grupo
        # Cinemark Hoyts, así que su número es estructuralmente más chico que
        # el histórico y la alarma saltaría todas las semanas.
        if not rancio and not es_comercial and base and base >= 5 and n < base * 0.4:
            flojos.append((cine, n, titulos, f"~{base:.0f}"))
            rep.cronicar(f"**{cine}** está por debajo de lo habitual: {_n(n, 'función', 'funciones')} de "
                         f"{_n(titulos, 'película', 'películas')}, contra ~{base:.0f} de siempre.",
                         cine=cine, regla="floja")

        if (cine not in SIN_REGLA_FALTANTES and probe_n and titulos
                and probe_n >= titulos * 3 and probe_n - titulos >= 4):
            rep.accionar(cine, f"la fuente publica {probe_n} {probe_detail} y "
                               f"nosotros tenemos {titulos} película(s). Puede "
                               f"estar faltando programación.", regla="faltantes")

    rep.tabla = flojos
    rep.sin_novedad = len([c for c in universo if fut.get(c)]) - len(flojos)


# Para decir que a una sala le falta la cartelera de hoy y de mañana: en
# cuántas de las últimas semanas hay que haberla medido, teniendo funciones
# esos mismos días de la semana en todas.
SEMANAS_MIN = 3
FUNCIONES_MIN = 4         # funciones que solía tener entre esos dos días
# Con cuántos días de programación por delante una sala "se está quedando
# corta", si suele tener al menos HORIZONTE_HABITUAL.
HORIZONTE_CORTO = 1
HORIZONTE_HABITUAL = 5


def check_rendimiento(rep: Report, filas: list, datos_frescos: bool = True) -> None:
    """Lo que el conteo de funciones no muestra (`filas`: el tablero de
    audit_fuentes): una sala llena de funciones lejanas y vacía para hoy, una
    fuente que anda un día sí y dos no, y las que se quedan sin programación.
    """
    cortas = []
    for r in filas:
        sala = r["sala"]
        if not r["n"]:
            continue
        # Una sala con funciones publicadas y ninguna para hoy ni para mañana,
        # cuando esos mismos días de la semana siempre tuvo: lo que entra es
        # programación lejana (preventas) y la de estos días no. Se compara
        # lunes con lunes, porque hay salas que cierran lunes y martes. Si la
        # fuente está caída ya lo dijo check_cobertura, y no se repite.
        #
        # Sólo para salas con volumen esos días: la Biblioteca del Congreso
        # da una función por día y arranca su ciclo del mes un miércoles sin
        # que nada esté roto.
        con, medidas, solia = r.get("mismos_dias") or (0, 0, 0)
        if (datos_frescos and r["scrapeadas"] and not r["hoy_y_manana"]
                and medidas >= SEMANAS_MIN and con == medidas and solia >= FUNCIONES_MIN):
            rep.accionar(sala, f"tiene {_n(r['n'], 'función publicada', 'funciones publicadas')} "
                               f"pero ninguna para hoy ni para mañana, y las últimas {medidas} "
                               f"semanas siempre tuvo para estos mismos días. Lo que está "
                               f"entrando es programación lejana (preventas): la cartelera de "
                               f"esta semana no.", regla="sin-hoy")
        if (r["horizonte"] is not None and r["horizonte"] >= HORIZONTE_HABITUAL
                and r["adelante"] is not None and r["adelante"] <= HORIZONTE_CORTO
                and not r["comercial"]):
            cortas.append(f"{sala} (hasta el {_dia_mes(r['hasta'])}; suele tener "
                          f"~{r['horizonte']:.0f} días por delante)")
        viva = r["viva"]
        if viva and r["scrapeadas"] and viva[1] >= 5 and viva[0] <= viva[1] - 2:
            rep.cronicar(f"**{sala}**: su fuente contestó {viva[0]} de los últimos {viva[1]} "
                         f"días. Hoy anda, pero viene fallando seguido.",
                         cine=sala, regla="fuente-inestable")
    if cortas:
        rep.cronicar("Se quedan sin programación entre hoy y mañana: " + ", ".join(cortas)
                     + ". Si su web ya publicó lo que sigue, el scraper no lo está viendo.",
                     regla="horizonte")


def check_cambios(rep: Report, screenings: list[dict], today: date,
                  snaps: dict[str, Counter], etiqueta: str = "") -> None:
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
    donde = f" ({etiqueta})" if etiqueta else ""

    # Prioridad por gravedad, no por tamaño: que un cine se caiga importa más
    # que uno que duplicó funciones, aunque el salto sea más chico.
    cambios: list[tuple[int, int, str]] = []
    for cine in set(antes) | set(ahora):
        a, b = antes.get(cine, 0), ahora.get(cine, 0)
        delta = abs(b - a)
        if b == 0 and a > 0:
            cambios.append((0, delta, f"**{cine}**{donde} desapareció: {a} → 0 funciones."))
        elif a >= 8 and b < a * 0.5:
            cambios.append((1, delta, f"**{cine}**{donde} bajó bastante: {a} → {b} funciones."))
        elif a == 0 and b > 0:
            cambios.append((2, delta, f"**{cine}**{donde} volvió a la cartelera: 0 → {b} funciones."))
        elif a >= 8 and b > a * 2:
            cambios.append((3, delta, f"**{cine}**{donde} subió bastante: {a} → {b} funciones."))

    cambios.sort(key=lambda c: (c[0], -c[1], c[2]))
    TOPE = 8
    for _, _, msg in cambios[:TOPE]:
        rep.cambiar(msg)
    if len(cambios) > TOPE:
        rep.cambiar(f"…y {len(cambios) - TOPE} cines más{donde} con cambios de tamaño "
                    f"parecido (corré `python3 scripts/audit.py` para verlos).")


def check_categorias(rep: Report, screenings: list[dict], today: date, *,
                     previas: list | tuple = (), festivales: Optional[list] = None,
                     salas: Optional[dict] = None, ciudad: str = "",
                     a_mano: Optional[set] = None, retenidas: Optional[list] = None) -> set:
    """Que cada dato esté en su casillero (las reglas viven en categorias.py).
    Devuelve los (sala, título) que marcó, para que el agente de fichas no
    repita el mismo título con otras palabras.

    `previas`: funciones de una corrida anterior, para conocer los ciclos que
    cada sala ya tenía. `retenidas`: lo que frenó el portero en el último
    scrape (cartelera.json, clave `retenidas`).
    """
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    mezclas = categorias.revisar(
        fut, previas=previas, festivales=festivales, salas=salas, ciudad=ciudad,
        a_mano=a_mano or (),
        excepcion=lambda regla, cine, valor, fila: rep.excepciones.cubre(regla, cine, valor))

    orden = list(categorias.REGLAS)
    # Lo que rompe la ficha publicada: una línea por sala, que es por donde se
    # arregla (cada sala tiene su scraper).
    por_sala: dict[tuple, list] = defaultdict(list)
    # Lo que sólo la afea: una línea por regla, con las salas adentro. Veinte
    # líneas de "un título con un tramo en mayúsculas" no dicen más que una.
    por_regla: dict[str, list] = defaultdict(list)
    for m in mezclas:
        if categorias.REGLAS[m.regla][0] == categorias.ERROR:
            por_sala[(m.regla, m.cine)].append(m)
        else:
            por_regla[m.regla].append(m)

    def cuenta(ms: list) -> str:
        funciones = sum(m.n for m in ms)
        return (_n(len(ms), "caso", "casos")
                + (f", {funciones} funciones" if funciones != len(ms) else ""))

    for (regla, cine), ms in sorted(por_sala.items(), key=lambda kv: (orden.index(kv[0][0]), kv[0][1])):
        _, que, hacer = categorias.REGLAS[regla]
        rep.accionar(cine, f"{que} ({cuenta(ms)}). {hacer[0].upper()}{hacer[1:]}. Por ejemplo: "
                           + "; ".join(m.detalle for m in ms[:3]),
                     regla=regla, ejemplos=[m.detalle for m in ms])
    for regla, ms in sorted(por_regla.items(), key=lambda kv: orden.index(kv[0])):
        _, que, hacer = categorias.REGLAS[regla]
        salas_n = Counter(m.cine for m in ms)
        donde = ", ".join(f"{c} ({n})" if n > 1 else c for c, n in sorted(salas_n.items()))
        rep.cronicar(f"{que[0].upper()}{que[1:]} ({cuenta(ms)}) en {donde}. {hacer[0].upper()}"
                     f"{hacer[1:]}. Por ejemplo: " + "; ".join(m.detalle for m in ms[:2]),
                     regla=regla, ejemplos=[f"{m.cine}: {m.detalle}" for m in ms])

    # Lo que el portero frenó en el último scrape: no salió a la web, pero que
    # haya algo que frenar quiere decir que un scraper no pudo leer un programa.
    frenadas: dict[str, list] = defaultdict(list)
    for r in retenidas or []:
        frenadas[r.get("cine", "?")].append(r)
    for cine, rs in sorted(frenadas.items()):
        titulos = []
        for r in rs:
            if r.get("title_es") not in titulos:
                titulos.append(r.get("title_es"))
        muestra = ", ".join(f"«{t}»" for t in titulos[:3]) + ("…" if len(titulos) > 3 else "")
        rep.accionar(cine, f"el portero frenó {_n(len(rs), 'función que no era una película', 'funciones que no eran películas')} "
                           f"({muestra}): eran nombres de ciclos o de festivales. No salieron "
                           f"a la web, pero quiere decir que el scraper no pudo leer el "
                           f"programa: hay que mirarlo.",
                     regla="retenidas", ejemplos=[r.get("motivo", "") for r in rs])
    return {(m.cine, m.fila.get("title_es", "")) for m in mezclas
            if m.regla.startswith("titulo-")}


def check_padron(rep: Report, salas: dict, prefijos_web: list, direcciones: set,
                 datos: dict) -> None:
    """Que la web y el código hablen de las mismas salas.

    Las cadenas están en una lista de prefijos que vive en tres lugares
    (index.html, run.py y categorias.py). Si una sala se suma en uno solo, la
    web la muestra como sala de arte, o el merge no le conserva las funciones.
    """
    if not salas:
        rep.revisado("el padrón de salas de index.html no se pudo leer")
        return
    rep.revisado(f"el padrón de index.html ({len(salas)} salas)")
    faltan_aca = sorted(set(prefijos_web) - set(COMMERCIAL_PREFIXES))
    faltan_alla = sorted(set(COMMERCIAL_PREFIXES) - set(prefijos_web))
    if prefijos_web and (faltan_aca or faltan_alla):
        partes = []
        if faltan_aca:
            partes.append(f"index.html tiene {', '.join(faltan_aca)} y categorias.py no")
        if faltan_alla:
            partes.append(f"categorias.py tiene {', '.join(faltan_alla)} e index.html no")
        rep.accionar("Cadenas", "la lista de cadenas no es la misma en la web y en el código: "
                                + "; ".join(partes) + ". Tiene que ser igual en index.html, "
                                "run.py y categorias.py.", regla="cadenas-distintas", ciudad="")
    sin_dir = sorted({s.get("cine", "") for _, filas in datos.values() for s in filas}
                     - direcciones) if direcciones else []
    if sin_dir:
        rep.cronicar("Salas con funciones y sin dirección en index.html (CINE_ADDRESSES): "
                     + ", ".join(sin_dir) + ".", regla="sin-direccion", ciudad="")


def check_festivales(rep: Report, screenings: list[dict], today: date, registro: list,
                     radar: list, manual: Optional[dict] = None,
                     web_estado: Optional[dict] = None, leer=None,
                     avanzar: bool = True) -> dict:
    """El monitor de festivales (audit_festivales.py). Arma la sección
    Festivales del informe y devuelve el estado nuevo de las webs."""
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    fichas, notas = monitor.revisar_registro(registro, fut, today, manual, ROOT)
    notas += monitor.revisar_radar(radar, fichas, today)
    notas_web, web_nuevo = monitor.revisar_webs(fichas, web_estado or {}, today,
                                                leer=leer, avanzar=avanzar)
    notas += notas_web
    vivos = [f for f in fichas if f["estado"] in ("en-curso", "proximo")]
    vigiladas = sum(1 for f in fichas if f["slug"] in web_nuevo)
    rep.revisado(f"{len(registro)} festivales del registro ({len(vivos)} vigentes), "
                 f"{len(radar)} del radar"
                 + (f" y {vigiladas} web{'s' if vigiladas != 1 else ''}" if leer else ""))

    por_festival: dict[str, list] = defaultdict(list)
    for n in notas:
        por_festival[n.slug].append(n)
        if n.sev == categorias.ERROR:
            rep.accionar(n.nombre, n.msg, regla=n.regla, efimero=n.efimera, ciudad="")
        else:
            rep.cronicar(f"**{n.nombre}**: {n.msg}", cine=n.nombre, regla=n.regla,
                         efimero=n.efimera, ciudad="")

    for ciclo, n, salas in monitor.sueltos(registro, fut):
        rep.cronicar(f"**{ciclo}** ({n} funciones en {', '.join(salas)}) aparece en la "
                     f"pestaña Festivales con el nombre del ciclo, porque dice «festival» y "
                     f"no está en data/festivales.json. Si es un festival, registrarlo con "
                     f"nombre, fechas y logo.", cine=ciclo, regla="suelto", ciudad="")

    # La sección: primero lo que está en curso, después lo que viene.
    orden = {"en-curso": 0, "proximo": 1}
    for f in sorted(vivos, key=lambda f: (orden[f["estado"]], f["desde"] or date.max)):
        cuando = ", ".join(x for x in (monitor.rango_texto(f["desde"], f["hasta"]),
                                       monitor.cuando_texto(f["estado"], f["desde"], f["hasta"], today)) if x)
        donde = f" en {f['lugar']}" if f["lugar"] else ""
        if f["n"]:
            cuerpo = (f"{_n(f['n'], 'función', 'funciones')} por delante en "
                      f"{_n(len(f['salas']), 'sala', 'salas')}"
                      + (" (página propia)" if f["archivo"] else ""))
        else:
            cuerpo = "sin funciones cargadas"
        pendientes = len(por_festival.get(f["slug"], []))
        cola = f" Tiene {pendientes} cosa{'s' if pendientes != 1 else ''} para mirar." if pendientes else ""
        rep.festivales.append(f"**{f['nombre']}**{donde} ({cuando}): {cuerpo}.{cola}")
    del_radar = [n for n in notas if n.regla.startswith("radar")]
    if del_radar:
        rep.festivales.append("En el radar y sin cargar: " + ", ".join(
            f"**{n.nombre}**" + (f" ({n.corto})" if n.corto else "") for n in del_radar) + ".")
    recientes = sorted((f for f in fichas if f["estado"] == "terminado" and f["hasta"]
                        and (today - f["hasta"]).days <= 14), key=lambda f: f["hasta"])
    if recientes:
        rep.festivales.append("Terminaron hace poco: " + ", ".join(
            f"{f['nombre']} (el {monitor.dia_mes(f['hasta'])})" for f in recientes) + ".")
    if not rep.festivales:
        rep.festivales.append("No hay festivales en curso ni por empezar en el registro, "
                              "y el radar no espera ninguno para estas semanas.")
    return web_nuevo


# Un director es un nombre, no una oración. Estas señales delatan que el parser
# se llevó el copete, la sinopsis o el nombre del ciclo en vez del crédito.
_DIR_FRASE = re.compile(r"\b(será|sera|proyecc|festival|presenta|con la|marco de|"
                        r"ciclo|entrada|función|funcion)\b", re.IGNORECASE)


def _norm_titulo(t: str) -> str:
    """Para comparar títulos: sin tildes, caja ni puntuación."""
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).split())


def check_calidad(rep: Report, screenings: list[dict], today: date,
                  ya_marcados: Optional[set] = None) -> None:
    """`ya_marcados`: los (sala, título) que el agente de categorías ya marcó.
    De esos no se vuelve a decir nada del título: es el mismo problema."""
    hoy = today.isoformat()
    anio_max = today.year + 2
    ya_marcados = ya_marcados or set()
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

        # Un título que en realidad son VARIAS películas, o una película más
        # una actividad. Pasó con el CCK, que arma programas dobles escribiendo
        # «A + B + charlas con Fulano» en una sola línea de la agenda: entraba
        # como una función con ese título entero.
        #
        # Lo que lo vuelve caro es que se lleva puesta la ficha completa —un
        # título compuesto no matchea contra la fuente ni contra Letterboxd, así
        # que la fila sale sin director, sin año y sin link— y que nadie se
        # entera: no falla nada, sólo queda una fila muda entre las buenas.
        # Por eso la regla mira el título y no el cine: el día que otra sala
        # escriba así, esto lo dice el lunes siguiente en vez de nunca.
        if (cine, s.get("title_es", "")) in ya_marcados:
            pass
        elif _TITULO_COMPUESTO.search(titulo) and not director:
            flag("título que son varias películas", cine, repr(titulo))
        # Título que en realidad es el copete/ciclo de la card.
        elif "·" in titulo or len(titulo) > 80:
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
            flag("sin link de entradas", cine, titulo)

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
        "título que son varias películas": "hay funciones cuyo título son varias "
                                           "películas juntas (o una película más "
                                           "una charla): así no matchean contra "
                                           "la fuente ni contra Letterboxd y "
                                           "quedan sin director, año ni link. "
                                           "Hay que desagregarlas en una fila "
                                           "por película",
    }
    menores: dict[str, list] = defaultdict(list)
    for (regla, cine), n in sorted(problemas.items(), key=lambda kv: (-kv[1], kv[0])):
        muestra = ejemplos[(regla, cine)][0]
        slug = _norm_titulo(regla).replace(" ", "-")
        if regla in QUE_HACER:
            veces = f" (×{n})" if n > 1 else ""
            rep.accionar(cine, f"{QUE_HACER[regla]}{veces}. Ejemplo: {muestra}",
                         regla=slug, ejemplos=ejemplos[(regla, cine)])
        else:
            menores[regla].append((cine, n, muestra))
    # Lo menor, una línea por regla con las salas adentro.
    for regla, casos in sorted(menores.items()):
        donde = ", ".join(f"{cine} ×{n}" for cine, n, _ in casos)
        rep.cronicar(f"{regla[0].upper()}{regla[1:]}: {donde}. Ejemplo ({casos[0][0]}): {casos[0][2]}",
                     regla=_norm_titulo(regla).replace(" ", "-"),
                     ejemplos=[f"{cine}: {m}" for cine, _, m in casos])


def check_completitud(rep: Report, screenings: list[dict], today: date) -> None:
    """Campos que no rompen nada pero degradan la ficha (y el post de IG)."""
    hoy = today.isoformat()
    fut = [s for s in screenings if s.get("fecha", "") >= hoy]
    por_cine = defaultdict(list)
    for s in fut:
        por_cine[s["cine"]].append(s)
    rep.revisado(f"{_miles(len(fut))} funciones de {CIUDADES.get(rep.ciudad, ('',))[0] or 'la cartelera'}")
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
            rep.cronicar(f"{total} funciones {etiqueta}: {', '.join(afectados)}.",
                         regla="sin-" + campo)

    # Filas peladas: sólo título y horario. Lo más probable es que no sean
    # películas (una charla, una inauguración) o que el scraper no haya podido
    # leer la ficha. Es la lista de trabajo del agente de categorías: son las
    # que hay que ir a leer a la fuente.
    peladas: dict[str, list] = defaultdict(list)
    for s in fut:
        if s["cine"].startswith(COMMERCIAL_PREFIXES):
            continue
        if not any(s.get(c) for c in ("director", "year", "duration", "letterboxd")):
            if s.get("title_es") not in peladas[s["cine"]]:
                peladas[s["cine"]].append(s.get("title_es"))
    if peladas:
        total = sum(len(v) for v in peladas.values())
        detalle = "; ".join(f"{cine}: " + ", ".join(f"«{t}»" for t in ts[:2])
                            + (f" y {len(ts) - 2} más" if len(ts) > 2 else "")
                            for cine, ts in sorted(peladas.items(), key=lambda kv: -len(kv[1])))
        rep.cronicar(f"{_n(total, 'título', 'títulos')} sin ningún dato (ni director, ni año, "
                     f"ni duración, ni Letterboxd): puede que no sean películas. {detalle}.",
                     regla="sin-ningun-dato",
                     ejemplos=[f"{c}: {t}" for c, ts in peladas.items() for t in ts])


# --------------------------------------------------------------------------
# La orquesta
# --------------------------------------------------------------------------

def _con(rep: Report, agente: str, ciudad: str, parte) -> None:
    """Corre la parte de un agente. Si se cae, queda dicho en el informe: lo
    que no se revisó no puede pasar por revisado."""
    rep.agente, rep.ciudad = agente, ciudad
    try:
        parte()
    except Exception as e:           # noqa: BLE001 (cualquier falla es un hallazgo)
        motivo = f"{type(e).__name__}: {e}"
        rep.caidos[agente] = motivo
        donde = f" de {CIUDADES[ciudad][0]}" if ciudad in CIUDADES else ""
        rep.accionar("", f"el agente de {AGENTES[agente][0].lower()} no pudo terminar su "
                         f"revisión{donde} ({motivo}). Lo que tenía a cargo quedó sin mirar.",
                     regla="agente-caido", agente=agente, ciudad=ciudad)
        if os.environ.get("AUDIT_DEBUG"):
            raise


def _cargar_ciudad(ciudad: str, hasta: Optional[str]) -> Optional[tuple]:
    """((meta, funciones), historia) de una ciudad, o None si no tiene archivo.
    Con `hasta`, la cartelera del último commit de ese día."""
    path = CIUDADES[ciudad][1]
    hist = Historia.de_git(ROOT, path, dias=120, detalle=8, hasta=hasta)
    if hasta:
        if not hist:
            return None
        payload = hist._leer(hist._shas[hist.dias[-1]]) or {}
        return (payload, payload.get("screenings", [])), hist
    try:
        return load_cartelera(ciudad), hist
    except FileNotFoundError:
        return None


def auditar(args, today: date) -> tuple[Report, dict]:
    """Corre los cinco agentes. Devuelve (informe, estado nuevo de las webs
    de los festivales)."""
    hoy = today.isoformat()
    rep = Report(Excepciones.de_archivo(EXCEPCIONES, today))
    replay = bool(args.como_si_fuera)
    en_linea = not args.offline and not replay

    salas, prefijos_web, direcciones = leer_padron()
    manual, a_mano = cargar_manual()
    registro, radar, web_estado = monitor.cargar(ROOT)
    claves_festival = sorted({categorias.norm(x) for f in registro
                              for x in [f.get("nombre"), f.get("ciclo")] + list(f.get("alias") or [])
                              if categorias.norm(x or "")}
                             | {categorias.norm(r.get("ciclo", "")) for r in manual.get("festivales", [])
                                if categorias.norm(r.get("ciclo", ""))})

    datos: dict = {}
    historias: dict = {}
    for ciudad in CIUDADES:
        if ciudad == "madrid" and args.sin_madrid:
            continue
        cargada = _cargar_ciudad(ciudad, args.como_si_fuera)
        if cargada:
            datos[ciudad], historias[ciudad] = cargada

    horas = [0.0]

    def frescura() -> None:
        horas[0] = check_frescura(rep, datos, today, medir_edad=not replay)
        if replay:
            rep.contexto = re.sub(r"^Datos de hace [^.]*\. ", "", rep.contexto)
            horas[0] = 0.0
            return
        check_stories(rep, today)
        if en_linea:
            check_corridas(rep, corridas_de_actions(today - timedelta(days=7)))
    _con(rep, "frescura", "", frescura)

    for ciudad, (meta, filas) in datos.items():
        nombre = CIUDADES[ciudad][0]
        hist = historias[ciudad]
        snaps = {d: hist.funciones[d] for d in hist.dias[-args.dias_historico:]}
        fut = [s for s in filas if s.get("fecha", "") >= hoy]
        padron = {s for s, c in salas.items() if c == ciudad}
        sondas = PROBES if ciudad == "ba" else {}

        def fuentes() -> None:
            if not hist:
                rep.cronicar("Sin línea de base histórica: el repo está clonado shallow. "
                             "En CI hace falta `actions/checkout` con `fetch-depth: 0`.",
                             regla="sin-historia")
            probes = run_probes(sorted(sondas)) if en_linea and sondas else {}
            check_cobertura(rep, filas, today, snaps, probes, meta.get("fuentes"),
                            largo=hist or None, padron=padron, sondas=sondas,
                            claves_festival=claves_festival)
            tabla = tablero_mod.tablero(
                hist, fut, meta.get("fuentes") or {}, today, padron=padron, a_mano=a_mano,
                es_comercial=lambda c: c.startswith(COMMERCIAL_PREFIXES))
            rep.tableros[ciudad] = tabla
            check_rendimiento(rep, tabla, datos_frescos=horas[0] <= 36)
            check_cambios(rep, filas, today, snaps, "Madrid" if ciudad == "madrid" else "")
            rep.revisado(f"{len(tabla)} salas de {nombre}"
                         + (f" con {len(probes)} sondas" if probes else "")
                         + (f" y {len(hist.dias)} días de historial" if hist else ""))
        _con(rep, "fuentes", ciudad, fuentes)

        marcados: set = set()

        def categorias_() -> None:
            dia = hist.cerca_de((today - timedelta(days=7)).isoformat(), 4) if hist else None
            previas = hist.filas(dia) if dia else []
            marcados.update(check_categorias(
                rep, filas, today, previas=previas,
                festivales=registro if ciudad == "ba" else [],
                salas=salas or None, ciudad=ciudad, a_mano=a_mano,
                retenidas=meta.get("retenidas")))
            if meta.get("portero"):
                rep.accionar("", f"el portero no pudo correr en el último scrape "
                                 f"({meta['portero']}): lo que se publicó no pasó por el "
                                 f"control que frena los ciclos puestos como películas. "
                                 f"Mirá el final de run.py.", regla="portero-caido")
            rep.revisado(f"{_miles(len(fut))} funciones de {nombre} contra "
                         f"{len(categorias.REGLAS)} reglas")
        _con(rep, "categorias", ciudad, categorias_)

        def fichas() -> None:
            check_calidad(rep, filas, today, marcados)
            check_completitud(rep, filas, today)
        _con(rep, "fichas", ciudad, fichas)

    _con(rep, "categorias", "", lambda: check_padron(rep, salas, prefijos_web, direcciones, datos))

    web_nuevo = [web_estado]

    def festivales() -> None:
        web_nuevo[0] = check_festivales(
            rep, datos["ba"][1] if "ba" in datos else [], today, registro, radar, manual,
            web_estado, leer=monitor.leer_web if en_linea else None,
            avanzar=not args.centinela)
    _con(rep, "festivales", "", festivales)
    return rep, web_nuevo[0]


def _a_json(rep: Report, today: date, estado: dict) -> dict:
    """El informe en datos, para los agentes de Claude y para la memoria."""
    return {
        "fecha": today.isoformat(),
        "generado": datetime.now().isoformat(timespec="seconds"),
        "veredicto": rep.veredicto,
        "contexto": rep.contexto,
        "hallazgos": [{"id": h.id, "sev": h.sev, "agente": h.agente, "ciudad": h.ciudad,
                       "cine": h.cine, "regla": h.regla, "msg": h.msg, "desde": h.desde,
                       "nuevo": h.nuevo, "ejemplos": h.ejemplos} for h in rep.hallazgos],
        "resueltos": rep.resueltos,
        "cambios": rep.cambios,
        "festivales": rep.festivales,
        "partes": {a: {"reviso": rep.partes.get(a, []), "caido": rep.caidos.get(a, "")}
                   for a in AGENTES},
        "tablero": rep.tableros,
        "estado": estado,
    }


def _escribir_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="sin red: ni sondas, ni webs de festivales, ni Actions")
    ap.add_argument("--out", type=Path, help="escribe el informe en un archivo")
    ap.add_argument("--html", type=Path,
                    help="además escribe el informe en HTML (para el mail semanal)")
    ap.add_argument("--json", type=Path,
                    help="escribe el informe en datos y guarda la memoria (data/audit.json)")
    ap.add_argument("--centinela", action="store_true",
                    help="pasada diaria: sólo avisa de los ERRORes que ayer no estaban")
    ap.add_argument("--alerta", type=Path,
                    help="con --centinela: dónde dejar el aviso en HTML, si hay algo nuevo")
    ap.add_argument("--como-si-fuera", metavar="YYYY-MM-DD",
                    help="audita la cartelera de ese día (sin red y sin memoria)")
    ap.add_argument("--sin-madrid", action="store_true", help="sólo Buenos Aires")
    ap.add_argument("--dias-historico", type=int, default=14,
                    help="snapshots de git para la línea de base (default 14)")
    args = ap.parse_args()

    today = date.fromisoformat(args.como_si_fuera) if args.como_si_fuera else date.today()
    rep, web_nuevo = auditar(args, today)

    # La memoria sale del archivo que se va a escribir o, si todavía no existe
    # (corriendo a mano, con --json a otra carpeta o sin él), de la del
    # repositorio: así el informe dice igual qué es nuevo, sin tocarla.
    estado_path = args.json if (args.json and args.json.exists()) else ESTADO
    previo = None if args.como_si_fuera else cargar_estado(estado_path)
    estado, estrenan = fechar(rep, previo, today)
    # La huella de las webs de los festivales va al lado del JSON: en el
    # workflow es data/festivales_web.json; a mano no pisa la del repositorio.
    webs_path = args.json.with_name(WEBS.name) if args.json else WEBS

    if args.centinela:
        # Sin memoria no hay "ayer" contra el que comparar: se guarda el estado
        # y no se avisa, que si no el primer día llega un mail con todo.
        nuevos = estrenan if previo is not None else []
        if nuevos:
            asunto, md = rep.alerta(nuevos, today)
            print(md)
            if args.alerta:
                args.alerta.write_text(f"<!-- asunto: {asunto} -->\n"
                                       f"<!-- fecha: {today.isoformat()} -->\n"
                                       + md_a_html(md) + "\n", encoding="utf-8")
        else:
            print(f"Centinela: nada nuevo ({rep.n_errors} cosas abiertas, todas conocidas).")
        if args.json:
            try:
                data = json.loads(args.json.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            data["estado"] = estado
            _escribir_json(args.json, data)
            _escribir_json(webs_path, web_nuevo)
        return 0

    informe = rep.render(today)
    print(informe)
    if args.out:
        args.out.write_text(informe + "\n", encoding="utf-8")
    if args.html:
        # Asunto y fecha van en comentarios HTML para que
        # scripts/mandar_auditoria.py no tenga que re-parsear el informe; la
        # fecha además le dice si el informe es de hoy.
        args.html.write_text(
            f"<!-- asunto: {rep.asunto(today)} -->\n"
            f"<!-- fecha: {today.isoformat()} -->\n"
            + md_a_html(informe) + "\n",
            encoding="utf-8")
    if args.json:
        _escribir_json(args.json, _a_json(rep, today, estado))
        if not args.como_si_fuera:
            _escribir_json(webs_path, web_nuevo)

    return 1 if rep.n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
