#!/usr/bin/env python3
"""TEMPORAL — corre el scraper de Sala Lúcida contra el sitio de verdad y
verifica los links de Letterboxd de lo que devuelve. Se borra junto con el
parche a probe-acceso.yml."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scraper import (LUCIDA_BASE, fetch_html, scrape_sala_lucida,   # noqa: E402
                     _lucida_parse_evento, _lucida_texto)
from verificar_letterboxd import verificar                          # noqa: E402
from datetime import date, timedelta                                # noqa: E402


def main() -> int:
    listing = fetch_html(LUCIDA_BASE + "/")
    links = []
    for a in listing.find_all("a", href=re.compile(r"/eventos/")):
        u = a["href"]
        u = u if u.startswith("http") else LUCIDA_BASE + u
        if u not in links:
            links.append(u)
    print(f"La home lista {len(links)} eventos.")
    texto = listing.get_text(" ", strip=True).lower()
    for pista in ("ver más", "ver mas", "siguiente", "cargar más", "página 2"):
        if pista in texto:
            print(f"  ⚠️  la home menciona {pista!r} — puede haber paginación")

    hoy, fin = date.today(), date.today() + timedelta(weeks=9)
    print("\nEventos que el scraper DESCARTA (no declaran dirección):")
    for u in links:
        soup = fetch_html(u)
        if _lucida_parse_evento(soup, u, hoy, fin):
            continue
        art = soup.select_one("main article")
        h2 = art.find("h2") if art else None
        f = art.select_one(".fecha h4") if art else None
        print(f"  · {_lucida_texto(h2) if h2 else '?'} "
              f"({_lucida_texto(f) if f else '?'}) {u}")

    funciones = scrape_sala_lucida(9)
    print(f"\n{len(funciones)} funciones\n" + "=" * 70)
    for s in sorted(funciones, key=lambda x: (x.fecha, x.hora)):
        print(f"{s.fecha} {s.hora}  {s.title!r} | dir={s.director!r} "
              f"año={s.year} dur={s.duration} ciclo={s.ciclo!r}")
        print(f"              {s.ticket_url}")

    pelis = {}
    for s in funciones:
        pelis.setdefault(s.title.lower(), s)

    print(f"\nVerificando {len(pelis)} película(s) contra Letterboxd\n" + "=" * 70)
    for clave, s in sorted(pelis.items()):
        print(f"\n• {s.title} — {s.director or '?'} ({s.year or '?'})")
        try:
            url, meta, fuerza = verificar(s.title, s.year, s.director, s.duration)
        except Exception as e:
            print(f"    error: {type(e).__name__}: {e}")
            continue
        if url:
            print(f'    OK ({fuerza}) "{clave}": "{url}",')
            print(f"       LB dice: {meta.get('director')!r} ({meta.get('year')})")
        else:
            print(f"    SIN CONFIRMAR — {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
