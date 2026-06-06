#!/usr/bin/env python3
"""
Vista previa LOCAL del scraper del Museo del Cine — sin tocar GitHub ni postear.

Uso:
    python3 scripts/preview_museo.py
    python3 scripts/preview_museo.py --semanas 9

Muestra, por cada nota mensual descubierta desde el índice:
  - la URL y el mes detectado
  - cuántos "headers" de día/hora matchean (p.ej. "Sábado 6 a las 16 h")
  - cuántas funciones se parsean efectivamente (header + línea de película)
  - el detalle de cada función dentro de la ventana de fechas
y un diagnóstico cuando hay headers que NO derivan en función (suele indicar
que cambió el formato de la línea de la película).
"""
import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import (  # noqa: E402
    _MUSEOCINE_MONTHS,
    _museocine_month_pages,
    _parse_museocine_page,
    fetch_html,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semanas", type=int, default=9, help="Ventana hacia adelante (default 9 ≈ 2 meses)")
    args = ap.parse_args()

    today = date.today()
    cutoff = today + timedelta(weeks=args.semanas)
    print(f"Hoy: {today}  ·  Ventana hasta: {cutoff}\n")

    urls = _museocine_month_pages()
    print(f"Notas descubiertas desde el índice: {len(urls)}")
    for u in urls:
        print(f"  - {u}")
    print()

    # Mismo regex de header que usa el parser, para contar matches crudos.
    header_re = re.compile(
        r"(?:Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+"
        r"(\d{1,2})\s+a\s+las\s+(\d{1,2})(?:[.:](\d{2}))?\s+h(?:s|oras)?",
        re.IGNORECASE,
    )

    total_en_ventana = 0
    for url in urls:
        slug_month = None
        for m_name, m_num in _MUSEOCINE_MONTHS.items():
            if f"/{m_name}-" in url:
                slug_month = m_num
                break
        try:
            soup = fetch_html(url)
        except Exception as e:
            print(f"⚠️  No se pudo descargar {url}: {e}\n")
            continue
        main_el = soup.find("article") or soup.find("main") or soup
        text = main_el.get_text("\n", strip=True)

        headers = header_re.findall(text)
        eventos = _parse_museocine_page(text, slug_month)
        en_ventana = [e for e in eventos if today <= date.fromisoformat(e["fecha"]) <= cutoff]
        total_en_ventana += len(en_ventana)

        mes = next((n for n, v in _MUSEOCINE_MONTHS.items() if v == slug_month), "?")
        print(f"📄 {url}")
        print(f"   mes detectado: {mes}  ·  headers día/hora: {len(headers)}  ·  "
              f"funciones parseadas: {len(eventos)}  ·  en ventana: {len(en_ventana)}")
        if len(headers) > len(eventos):
            print(f"   ⚠️  {len(headers) - len(eventos)} header(s) sin función → "
                  f"probable cambio de formato en la línea de la película")
        for e in en_ventana:
            extra = f" | {e['ciclo']}" if e.get("ciclo") else ""
            print(f"     · {e['fecha']} {e['hora']}  {e['title']}"
                  f"{' — ' + e['director'] if e.get('director') else ''}{extra}")
        print()

    print(f"TOTAL funciones del Museo del Cine en ventana: {total_en_ventana}")


if __name__ == "__main__":
    main()
