#!/usr/bin/env python3
"""
Test local SOLO del scraper de Centro Cultural Borges, sin correr todo run.py
ni esperar el CI.

Uso (desde la raíz del repo, en tu Mac):

    python3 test_borges.py              # 9 semanas hacia adelante
    python3 test_borges.py --semanas 4

Abre un Chrome VISIBLE (headful) — vas a ver cómo navega y pasa (o no) el
challenge anti-bots del sitio. En tu Mac usa tu display e IP reales, así que
debería comportarse como tu navegador normal (a diferencia del runner de CI,
que es headless y queda atrapado en la verificación de seguridad).

Requisitos locales (una sola vez):
    pip install -r requirements.txt
    playwright install chromium
"""
import argparse
import asyncio

from scraper import scrape_borges


async def main(semanas: int) -> None:
    print(f"🎬 Probando Centro Cultural Borges (semanas={semanas})...\n")
    # scrape_borges abre su propio navegador headful; el primer argumento (page)
    # se ignora, así que le pasamos None.
    funciones = await scrape_borges(None, semanas=semanas)

    print(f"\n{'='*70}\n{len(funciones)} funciones encontradas\n{'='*70}")
    # Agrupar por película para leerlo cómodo.
    por_peli: dict[str, list] = {}
    for s in funciones:
        por_peli.setdefault(s.title, []).append(s)
    for title, ss in por_peli.items():
        meta = ss[0]
        extra = ", ".join(filter(None, [
            meta.director or "",
            f"{meta.duration} min" if meta.duration else "",
        ]))
        print(f"\n• {title}" + (f"  ({extra})" if extra else ""))
        for s in sorted(ss, key=lambda x: (x.fecha, x.hora)):
            print(f"    {s.fecha}  {s.hora}")

    if not funciones:
        print("\n⚠️  0 funciones. Mirá la línea de diagnóstico de arriba "
              "([listado vacío; pantalla: '...']) para ver qué mostró el sitio.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--semanas", type=int, default=9)
    args = ap.parse_args()
    asyncio.run(main(args.semanas))
