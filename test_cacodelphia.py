#!/usr/bin/env python3
"""
Test local del scraper de Cacodelphia por mail, sin correr todo run.py ni abrir
un navegador: lee la casilla, parsea los newsletters e imprime la cartelera.

Uso (desde la raíz del repo):

    export GMAIL_USER='vos@gmail.com'
    export GMAIL_APP_PASSWORD='xxxx xxxx xxxx xxxx'
    python3 test_cacodelphia.py
    python3 test_cacodelphia.py --dias 60     # mirar más atrás en la casilla

GMAIL_APP_PASSWORD NO es la contraseña de la cuenta: es una "contraseña de
aplicación" de 16 caracteres que se genera en myaccount.google.com → Seguridad
→ Contraseñas de aplicación, y hace falta tener la verificación en dos pasos
activada. En CI va como secret del repo con el mismo nombre.

Sólo lee, y abre la casilla en readonly: no marca nada como leído.

Ojo que esto NO es la cartelera final — falta la unión con la SPA (funciones
sueltas más adelante) y la metadata de las fichas, que arma scrape_cacodelphia.
"""
import argparse
import os
import sys

from scraper import scrape_cacodelphia_mail


def main(dias: int) -> int:
    if not (os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")):
        print("⚠️  Faltan GMAIL_USER / GMAIL_APP_PASSWORD — ver el docstring de arriba.")
        return 1

    print(f"📬 Leyendo newsletters de Cacodelphia (últimos {dias} días)...\n")
    funciones = scrape_cacodelphia_mail(dias)

    if not funciones:
        print("⚠️  0 funciones. O la casilla no tiene newsletters recientes, o el\n"
              "    mail cambió de formato. Probá con --dias 60 para descartar lo\n"
              "    primero antes de tocar el parser.")
        return 1

    fechas = sorted({s.fecha for s in funciones})
    print(f"{'='*70}\n{len(funciones)} funciones · {len({s.title for s in funciones})} "
          f"películas · {fechas[0]} → {fechas[-1]}\n{'='*70}")

    por_peli: dict[str, list] = {}
    for s in funciones:
        por_peli.setdefault(s.title, []).append(s)

    for title, ss in por_peli.items():
        ciclo = f"  [ciclo: {ss[0].ciclo}]" if ss[0].ciclo else ""
        print(f"\n• {title}{ciclo}")
        for s in sorted(ss, key=lambda x: (x.fecha, x.hora)):
            print(f"    {s.fecha}  {s.hora}")
        print(f"    ↳ {ss[0].ticket_url}")

    # Una función por día suelta suele ser un rango que no se expandió.
    print(f"\n{'='*70}\nFunciones por día:")
    for f in fechas:
        print(f"  {f}  {sum(1 for s in funciones if s.fecha == f):2d}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    args = ap.parse_args()
    sys.exit(main(args.dias))
