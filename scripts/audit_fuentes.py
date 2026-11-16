#!/usr/bin/env python3
"""
El tablero de fuentes: cómo viene rindiendo la web de cada sala.

La auditoría ya comparaba cada sala contra sus últimos 14 días. Con eso se le
escapaban tres cosas, y las tres ya pasaron:

  - Una sala caída hace más que la ventana no tiene con qué compararse y
    desaparece del informe. El CEA dejó de traer funciones el 17/10/2026,
    después de tres meses programando todas las semanas, y un mes más tarde
    ningún informe lo nombraba.
  - Una sala que publica de caché se ve llena. Los Cines Ideal de Madrid
    llevaban una semana con las mismas 30 funciones (preventas de diciembre) y
    ninguna para hoy ni mañana.
  - Madrid no se miraba: Princesa, Renoir Plaza de España y Renoir Retiro
    estaban en cero desde el 13/11/2026.

Acá se lee el historial largo de cada cartelera (los commits de su JSON) y se
arma, por sala, lo que hace falta para verlo: cuántas funciones tuvo cada día,
hasta qué fecha llegaba su programación, cuántos días estuvo viva su fuente y
desde cuándo no publica nada.

Sólo stdlib. Usa git: sin historia (clone shallow) devuelve una Historia vacía.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Optional

_ES_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# De menos a más: una función ese día es el primer escalón, no un espacio.
_BARRAS = "▁▂▃▄▅▆▇█"
SIN_NADA = "_"


def chispa(serie: list) -> str:
    """Una barrita por día, a escala de la propia sala: "▇▆▅▃▂__▇▆▅"."""
    tope = max([v for v in serie if v] or [0])
    if not tope:
        return SIN_NADA * len(serie)
    out = []
    for v in serie:
        if not v:
            out.append(SIN_NADA)
        else:
            out.append(_BARRAS[min(len(_BARRAS) - 1, int(v / tope * (len(_BARRAS) - 1) + 0.5))])
    return "".join(out)


class Historia:
    """Lo que publicó cada sala día por día, según los commits de su cartelera.

    De cada día se toma el último commit (como la línea de base de siempre).
    De los días más recientes se leen además todos los commits, para saber si
    en ALGUNA corrida de ese día la fuente contestó: el pase de la tarde
    saltea a propósito el CCK y el Borges (--sin-proxy), así que mirar una
    sola corrida los daría por caídos todos los días.
    """

    def __init__(self) -> None:
        self.dias: list[str] = []                  # del más viejo al más nuevo
        self.funciones: dict[str, Counter] = {}    # día → futuras por sala
        self.del_dia: dict[str, Counter] = {}      # día → funciones con fecha de ese día
        self.hasta: dict[str, dict] = {}           # día → {sala: última fecha con funciones}
        self.viva: dict[str, dict] = {}            # día → {sala: ¿scrapeó algo en alguna corrida?}
        self.motivo: dict[str, dict] = {}          # día → {sala: por qué no (fuente_caida)}
        self._shas: dict[str, str] = {}
        self._root: Optional[Path] = None
        self._path = ""

    def __bool__(self) -> bool:
        return bool(self.dias)

    # ── Carga ─────────────────────────────────────────────────────────────
    @classmethod
    def de_git(cls, root: Path, path: str, dias: int = 120, detalle: int = 8,
               hasta: Optional[str] = None) -> "Historia":
        """`hasta` (YYYY-MM-DD): ignora los commits posteriores a ese día, para
        volver a correr la auditoría como si fuera ese día."""
        h = cls()
        h._root, h._path = root, path
        try:
            log = subprocess.run(
                ["git", "-C", str(root), "log", "--format=%H %ad",
                 "--date=format:%Y-%m-%d", "--", path],
                capture_output=True, text=True, timeout=60, check=True).stdout
        except Exception:
            return h
        por_dia: dict[str, list[str]] = {}
        for line in log.splitlines():
            partes = line.split()
            if len(partes) != 2:
                continue
            sha, dia = partes
            if hasta and dia > hasta:
                continue
            por_dia.setdefault(dia, []).append(sha)     # el más nuevo primero
            if len(por_dia) > dias:
                por_dia.pop(dia)
                break
        if len(por_dia) < 3:        # sin historia que valga (clone shallow)
            return h
        recientes = set(sorted(por_dia, reverse=True)[:detalle])
        for dia in sorted(por_dia):
            shas = por_dia[dia]
            ultimo = h._leer(shas[0])
            if ultimo is None:
                continue
            h._shas[dia] = shas[0]
            h.registrar(dia, ultimo)
            if dia in recientes:
                for sha in shas[1:]:
                    otro = h._leer(sha)
                    if otro is not None:
                        h.registrar_fuentes(dia, otro.get("fuentes"))
        h.dias = sorted(h.funciones)
        return h

    def _leer(self, sha: str) -> Optional[dict]:
        try:
            blob = subprocess.run(
                ["git", "-C", str(self._root), "show", f"{sha}:{self._path}"],
                capture_output=True, text=True, timeout=60, check=True).stdout
            return json.loads(blob)
        except Exception:
            return None

    def registrar(self, dia: str, payload: dict) -> None:
        """Suma el snapshot de un día (también lo usan los tests)."""
        fut: Counter = Counter()
        hoy: Counter = Counter()
        hasta: dict = {}
        for s in payload.get("screenings", []):
            f, cine = s.get("fecha", ""), s.get("cine", "")
            if f < dia:
                continue
            fut[cine] += 1
            if f == dia:
                hoy[cine] += 1
            # Una fecha que no es una fecha ("Sin fecha", de un scraper que no
            # pudo leerla) cuenta como función, pero no dice hasta cuándo hay.
            if _ES_FECHA.match(f) and f > hasta.get(cine, ""):
                hasta[cine] = f
        self.funciones[dia] = fut
        self.del_dia[dia] = hoy
        self.hasta[dia] = hasta
        self.registrar_fuentes(dia, payload.get("fuentes"))
        if dia not in self.dias:
            self.dias = sorted(self.funciones)

    def registrar_fuentes(self, dia: str, fuentes: Optional[dict]) -> None:
        if not isinstance(fuentes, dict):
            return
        viva = self.viva.setdefault(dia, {})
        motivo = self.motivo.setdefault(dia, {})
        for cine, f in fuentes.items():
            viva[cine] = viva.get(cine, False) or bool(f.get("scrapeadas"))
            if f.get("fuente_caida"):
                motivo[cine] = f["fuente_caida"]

    def filas(self, dia: str) -> list:
        """Las funciones de un día del historial (relee el commit)."""
        sha = self._shas.get(dia)
        payload = self._leer(sha) if sha and self._root else None
        return (payload or {}).get("screenings", [])

    # ── Lecturas ──────────────────────────────────────────────────────────
    def salas(self, ventana: int = 0) -> set:
        dias = self.dias[-ventana:] if ventana else self.dias
        return {c for d in dias for c, n in self.funciones[d].items() if n}

    def serie(self, sala: str, n: int = 28) -> list:
        return [self.funciones[d].get(sala, 0) for d in self.dias[-n:]]

    def cerca_de(self, objetivo: str, tolerancia: int = 3) -> Optional[str]:
        """El día con snapshot más cercano a `objetivo`, o None si queda lejos."""
        if not self.dias:
            return None
        o = date.fromisoformat(objetivo)
        d = min(self.dias, key=lambda x: abs((date.fromisoformat(x) - o).days))
        return d if abs((date.fromisoformat(d) - o).days) <= tolerancia else None

    def ultimo_con_funciones(self, sala: str) -> Optional[str]:
        for d in reversed(self.dias):
            if self.funciones[d].get(sala):
                return d
        return None

    def primero_con_funciones(self, sala: str) -> Optional[str]:
        for d in self.dias:
            if self.funciones[d].get(sala):
                return d
        return None

    def presencia(self, sala: str, ventana: int = 60) -> float:
        """De los días que la sala lleva en el historial (hasta su última
        función, y no más de `ventana`), en qué proporción tuvo funciones."""
        ult, pri = self.ultimo_con_funciones(sala), self.primero_con_funciones(sala)
        if not ult or not pri:
            return 0.0
        dias = [d for d in self.dias if pri <= d <= ult][-ventana:]
        return sum(1 for d in dias if self.funciones[d].get(sala)) / len(dias) if dias else 0.0

    def dias_de_vida(self, sala: str) -> int:
        ult, pri = self.ultimo_con_funciones(sala), self.primero_con_funciones(sala)
        if not ult or not pri:
            return 0
        return (date.fromisoformat(ult) - date.fromisoformat(pri)).days + 1

    def habitual(self, sala: str, ventana: int = 28) -> float:
        """Cuántas funciones tiene cuando anda: la mediana de los días en que
        tuvo algo, en la ventana que termina en su última función."""
        ult = self.ultimo_con_funciones(sala)
        if not ult:
            return 0.0
        vals = [self.funciones[d].get(sala, 0) for d in self.dias if d <= ult][-ventana:]
        vals = [v for v in vals if v]
        return median(vals) if vals else 0.0

    def horizonte_habitual(self, sala: str, ventana: int = 28) -> Optional[float]:
        """Con cuántos días de anticipación suele tener programación."""
        hs = []
        for d in self.dias[-ventana:]:
            ult = self.hasta[d].get(sala)
            if ult:
                hs.append((date.fromisoformat(ult) - date.fromisoformat(d)).days)
        return median(hs) if len(hs) >= 7 else None

    def diaria(self, sala: str, ventana: int = 28) -> float:
        """Proporción de días (de la ventana) en que tuvo funciones para ese
        mismo día: cerca de 1 es una sala que proyecta todos los días."""
        dias = self.dias[-ventana:]
        return sum(1 for d in dias if self.del_dia[d].get(sala)) / len(dias) if dias else 0.0

    def mismos_dias(self, sala: str, hoy: date, semanas: int = 4) -> tuple:
        """(semanas en que tuvo funciones, semanas medidas, cuántas funciones
        solía tener) para el mismo día de la semana que hoy o que mañana, en
        las últimas `semanas`.

        Sirve para no confundir una sala que cierra los lunes con una que
        dejó de traer la cartelera de estos días: se compara lunes con lunes.
        """
        con = medidas = 0
        cuantas = []
        for k in range(1, semanas + 1):
            vistos = []
            for delta in (0, 1):
                d = (hoy + timedelta(days=delta - 7 * k)).isoformat()
                if d in self.del_dia:
                    vistos.append(self.del_dia[d].get(sala, 0))
            if vistos:
                medidas += 1
                con += any(vistos)
                cuantas.append(sum(vistos))
        return con, medidas, (median(cuantas) if cuantas else 0)

    def dias_viva(self, sala: str, n: int = 7) -> Optional[tuple]:
        """(días con la fuente viva, días medidos) en los últimos n días con
        datos de procedencia; None si no hay."""
        dias = [d for d in self.dias if d in self.viva][-n:]
        medidos = [d for d in dias if sala in self.viva[d]]
        if not medidos:
            return None
        return sum(1 for d in medidos if self.viva[d][sala]), len(medidos)

    def racha_caida(self, sala: str) -> int:
        """Cuántos días seguidos, hasta el último, lleva sin scrapear nada."""
        n = 0
        for d in reversed([d for d in self.dias if d in self.viva]):
            if sala not in self.viva[d] or self.viva[d][sala]:
                break
            n += 1
        return n

    def ultimo_motivo(self, sala: str) -> str:
        for d in reversed(self.dias):
            m = self.motivo.get(d, {}).get(sala)
            if m:
                return m
        return ""


def dias_entre(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def tablero(hist: Historia, filas: list, fuentes: dict, hoy: date,
            padron: Optional[set] = None, a_mano: Optional[set] = None,
            es_comercial=lambda cine: False) -> list:
    """Una fila por sala, con todo lo que hace falta para leer cómo viene.

    `filas`: las funciones de hoy en adelante. `padron`: las salas que la web
    conoce para esta ciudad (sus chips): entran aunque no tengan nada, que es
    justamente cuando hay que verlas. `a_mano`: (sala, fecha, hora) de las
    funciones cargadas a mano.
    """
    hoy_s = hoy.isoformat()
    por_sala: dict[str, list] = {}
    for s in filas:
        por_sala.setdefault(s.get("cine", ""), []).append(s)
    universo = set(por_sala) | hist.salas(28) | set(padron or ()) | set(fuentes or {})
    hace7 = hist.cerca_de((hoy - timedelta(days=7)).isoformat()) if hist else None
    out = []
    for sala in universo:
        ss = por_sala.get(sala, [])
        n = len(ss)
        hasta = max((s.get("fecha", "") for s in ss if _ES_FECHA.match(s.get("fecha", ""))),
                    default="")
        f = (fuentes or {}).get(sala) or {}
        manuales = sum(1 for s in ss if (s.get("cine", ""), s.get("fecha", ""), s.get("hora", ""))
                       in (a_mano or ()))
        ult = hist.ultimo_con_funciones(sala) if hist else None
        fila = {
            "sala": sala,
            "comercial": es_comercial(sala),
            "n": n,
            "titulos": len({s.get("title_es", "") for s in ss}),
            "hasta": hasta,
            "adelante": dias_entre(hoy_s, hasta) if hasta else None,
            "hoy_y_manana": sum(1 for s in ss if s.get("fecha", "") <= (hoy + timedelta(days=1)).isoformat()),
            "hace7": hist.funciones[hace7].get(sala, 0) if hace7 else None,
            "habitual": hist.habitual(sala) if hist else 0.0,
            "horizonte": hist.horizonte_habitual(sala) if hist else None,
            "diaria": hist.diaria(sala) if hist else 0.0,
            "mismos_dias": hist.mismos_dias(sala, hoy) if hist else (0, 0, 0),
            "viva": hist.dias_viva(sala) if hist else None,
            "racha_caida": hist.racha_caida(sala) if hist else 0,
            "motivo": f.get("fuente_caida") or (hist.ultimo_motivo(sala) if hist and not f.get("scrapeadas") else ""),
            "scrapeadas": f.get("scrapeadas"),
            "publicadas": f.get("publicadas"),
            "a_mano": manuales,
            "serie": hist.serie(sala) if hist else [],
            "ultimo": ult,
            "sin_funciones_hace": dias_entre(ult, hoy_s) if (ult and not n) else (None if n else -1),
            "presencia": hist.presencia(sala) if hist else 0.0,
            "vida": hist.dias_de_vida(sala) if hist else 0,
        }
        out.append(fila)
    out.sort(key=lambda r: (r["comercial"], -r["n"], r["sala"]))
    return out
