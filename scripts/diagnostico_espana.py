#!/usr/bin/env python3
"""
¿Se puede entrar a sitedigo.com desde España, ahora mismo?

    python3 scripts/diagnostico_espana.py
    python3 scripts/diagnostico_espana.py --objetivo otro.dominio.com

Existe porque "se cae desde España" no se ve desde ningún lado nuestro: el
runner de GitHub está en EE.UU. y desde Argentina el sitio anda. Desde
diciembre de 2024 un juzgado de Barcelona deja que LaLiga le pida a Movistar,
Vodafone, Orange, Digi y compañía que bloqueen las IPs desde donde se ve
fútbol pirata, y como esas webs se esconden detrás de Cloudflare, en días de
partido se bloquean IPs compartidas de Cloudflare enteras. Con ellas caen
todos los sitios que salen por esas IPs, el nuestro incluido.

Para verlo de verdad hacen falta conexiones españolas de casa, y eso lo da
Globalping (api.globalping.io): sondas de voluntarios, muchas en las redes
residenciales de cada operadora. Por cada operadora pide el sitio, y con las
mismas sondas pide además dos controles:

  - github.com, que dice si la sonda tiene internet (si eso falla, la sonda no
    sirve y no cuenta);
  - pages.github.com, que sale por las IPs de GitHub Pages, adonde se mudaría
    el sitio si el problema son las IPs de Cloudflare.

Además: qué IPs tiene hoy el dominio en el DNS, si son de Cloudflare, y qué
dice hayahora.futbol (que mide los bloqueos de LaLiga IP por IP) de esas IPs.

Sin GLOBALPING_TOKEN alcanza (250 pruebas por hora por IP); con token, más.
"""
import argparse
import ipaddress
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

GLOBALPING = "https://api.globalping.io/v1/measurements"

# Las redes de casa que aplican los bloqueos. O2 va por la red de Movistar,
# Lowi por la de Vodafone, Simyo y Jazztel por las de MasOrange.
OPERADORAS = [
    ("Movistar / O2", 3352),
    ("Vodafone / Lowi", 12430),
    ("Orange", 12479),
    ("Jazztel (MasOrange)", 12715),
    ("Digi", 57269),
]
SONDAS_POR_OPERADORA = 3
CONTROL_RED = "github.com"
CONTROL_PAGES = "pages.github.com"

summary_lines = []


def out(line: str = "") -> None:
    print(line)
    summary_lines.append(line)


def http_json(url: str, body: dict | None = None, timeout: int = 30):
    headers = {"Accept": "application/json", "User-Agent": "sitedigo-diagnostico"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    token = os.environ.get("GLOBALPING_TOKEN")
    if token and url.startswith(GLOBALPING):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None


# ── DNS e IPs ─────────────────────────────────────────────────────────────

def ips_de(host: str) -> list[str]:
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
    except socket.gaierror as e:
        out(f"- `{host}`: no resuelve ({e})")
        return []


def rangos_cloudflare() -> list:
    redes = []
    for v in ("ips-v4", "ips-v6"):
        try:
            req = urllib.request.Request(f"https://www.cloudflare.com/{v}",
                                         headers={"User-Agent": "sitedigo-diagnostico"})
            with urllib.request.urlopen(req, timeout=20) as r:
                redes += [ipaddress.ip_network(l.strip()) for l in r.read().decode().split() if l.strip()]
        except Exception as e:
            out(f"- no pude bajar los rangos de Cloudflare ({v}): {e}")
    return redes


def es_cloudflare(ip: str, redes: list) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr.version == n.version and addr in n for n in redes)


# ── hayahora.futbol ───────────────────────────────────────────────────────

def hayahora(ips: dict[str, str]) -> None:
    """Qué IPs bloquea LaLiga ahora, según hayahora.futbol. Es un proyecto de
    terceros y su formato puede cambiar: si no lo entiende, avisa y sigue."""
    status, data = http_json("https://hayahora.futbol/estado/data.json")
    if status != 200 or not isinstance(data, dict):
        out(f"- hayahora.futbol no contestó como se esperaba (HTTP {status}).")
        return
    filas = data.get("data")
    if not isinstance(filas, list):
        out(f"- hayahora.futbol cambió de formato; claves: {sorted(data)[:10]}")
        return
    bloqueadas = {}
    for f in filas:
        cambios = f.get("stateChanges") or []
        if cambios and cambios[-1].get("state"):
            bloqueadas.setdefault(f.get("ip"), set()).add(f.get("isp") or "?")
    out(f"- hayahora.futbol (actualizado {data.get('lastUpdate', '?')}): "
        f"{len(bloqueadas)} IPs bloqueadas ahora mismo en alguna operadora.")
    for ip, donde in ips.items():
        if ip in bloqueadas:
            out(f"  - **`{ip}` ({donde}) está BLOQUEADA ahora en: "
                f"{', '.join(sorted(bloqueadas[ip]))}**")
        else:
            out(f"  - `{ip}` ({donde}) no figura bloqueada ahora mismo.")


# ── Globalping ────────────────────────────────────────────────────────────

def medir(target: str, locations) -> tuple[str | None, str]:
    body = {
        "type": "http",
        "target": target,
        "locations": locations,
        "measurementOptions": {"protocol": "HTTPS", "request": {"method": "HEAD", "path": "/"}},
    }
    status, data = http_json(GLOBALPING, body)
    if status != 202 or not data:
        err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
        return None, f"HTTP {status}: {err.get('message') or err.get('type') or data}"
    return data["id"], ""


def esperar(mid: str) -> list:
    for _ in range(40):
        time.sleep(3)
        status, data = http_json(f"{GLOBALPING}/{mid}")
        if status == 200 and data and data.get("status") != "in-progress":
            return data.get("results") or []
    return []


def veredicto(res: dict) -> tuple[bool, str]:
    r = res.get("result") or {}
    code = r.get("statusCode")
    if r.get("status") == "finished" and code:
        return True, f"HTTP {code} ({r.get('resolvedAddress') or '?'})"
    raw = (r.get("rawOutput") or r.get("status") or "?").strip().splitlines()
    return False, f"FALLA: {raw[0][:90] if raw else '?'} ({r.get('resolvedAddress') or '?'})"


def probar_operadora(nombre: str, asn: int, objetivo: str) -> dict:
    mid, err = medir(objetivo, [{"country": "ES", "asn": asn, "limit": SONDAS_POR_OPERADORA}])
    if not mid:
        out(f"| {nombre} | — | sin sondas o error: {err} | | |")
        return {"sondas": 0, "ips": set()}
    principal = esperar(mid)
    # Las mismas sondas, contra los controles: así una falla del sitio no se
    # confunde con una sonda sin internet.
    controles = {}
    for host in (CONTROL_RED, CONTROL_PAGES):
        cid, _ = medir(host, mid)
        controles[host] = esperar(cid) if cid else []

    def clave(x):
        p = x.get("probe") or {}
        return (p.get("asn"), p.get("city"), p.get("network"))

    def emparejar(res, lista):
        for j, x in enumerate(lista):
            if clave(x) == clave(res):
                return lista.pop(j)
        return None

    cuenta = {"sondas": 0, "sitio_ok": 0, "pages_ok": 0, "ips": set()}
    for res in principal:
        p = res.get("probe") or {}
        ok_sitio, txt_sitio = veredicto(res)
        if (res.get("result") or {}).get("resolvedAddress"):
            cuenta["ips"].add(res["result"]["resolvedAddress"])
        red = emparejar(res, controles[CONTROL_RED])
        pag = emparejar(res, controles[CONTROL_PAGES])
        ok_red = veredicto(red)[0] if red else False
        ok_pag, txt_pag = veredicto(pag) if pag else (False, "sin dato")
        sonda = f"{p.get('city', '?')} · {p.get('network', '?')} (AS{p.get('asn', '?')})"
        if not ok_red:
            out(f"| {nombre} | {sonda} | sonda sin internet, no cuenta | | |")
            continue
        cuenta["sondas"] += 1
        cuenta["sitio_ok"] += ok_sitio
        cuenta["pages_ok"] += ok_pag
        out(f"| {nombre} | {sonda} | {'✅' if ok_sitio else '❌'} {txt_sitio} | ✅ | "
            f"{'✅' if ok_pag else '❌'} {txt_pag} |")
    return cuenta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--objetivo", default="sitedigo.com")
    args = ap.parse_args()
    objetivo = args.objetivo

    out(f"## Diagnóstico de {objetivo} desde España")
    out(f"_{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_")
    out()
    out("### DNS")
    redes_cf = rangos_cloudflare()
    ips = {}
    for host in (objetivo, f"www.{objetivo}"):
        for ip in ips_de(host):
            cf = es_cloudflare(ip, redes_cf) if redes_cf else None
            out(f"- `{host}` → `{ip}`" + (" — **IP compartida de Cloudflare**" if cf else ""))
            if host == objetivo:
                ips[ip] = "DNS desde el runner"
    out()
    out("### Desde redes españolas (Globalping)")
    out(f"| Operadora | Sonda | {objetivo} | {CONTROL_RED} | {CONTROL_PAGES} (GitHub Pages) |")
    out("|---|---|---|---|---|")
    total = {"sondas": 0, "sitio_ok": 0, "pages_ok": 0}
    for nombre, asn in OPERADORAS:
        c = probar_operadora(nombre, asn, objetivo)
        for k in total:
            total[k] += c.get(k, 0)
        # Cloudflare no le da a España las mismas IPs que al runner: las que
        # importan para el bloqueo son las que resolvieron las sondas.
        for ip in sorted(c.get("ips", ())):
            ips.setdefault(ip, "así resuelve desde España")
    out()
    out("### hayahora.futbol")
    hayahora(ips)
    out()
    out("### Veredicto")
    n = total["sondas"]
    if not n:
        out("No hubo sondas útiles: no se puede concluir nada desde acá.")
    else:
        out(f"- {objetivo}: entra en {total['sitio_ok']}/{n} conexiones españolas.")
        out(f"- GitHub Pages: entra en {total['pages_ok']}/{n}.")
        if total["sitio_ok"] < n and total["pages_ok"] == n:
            out("- **El sitio falla donde GitHub Pages entra: el problema son las IPs, "
                "no el contenido.**")
        elif total["sitio_ok"] == n:
            out("- Ahora mismo entra en todas. Los bloqueos de LaLiga van y vienen con los "
                "partidos: si hoy no hay, correlo de nuevo durante uno.")

    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write("\n".join(summary_lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
