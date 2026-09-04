#!/usr/bin/env python3
"""
Test de la memoria de eventos del CTBA (Sala Lugones), sin red.

    python3 test_ctba_memoria.py

El caso: el listado de complejoteatral.gob.ar saca la tarjeta de un ciclo antes
de que el ciclo termine. La Integral Pere Portabella desapareció del listado el
1/9/2026 con funciones el 2 y el 3 todavía por delante, y como el scraper sólo
conocía lo que el listado le mostraba, esas cinco funciones se borraron de la
cartelera — el jueves 3 el Lugones figuraba con una sola función teniendo tres.

La página /ver/ del ciclo seguía en pie (tres días después del final todavía
servía el programa entero), así que la memoria guarda los eventos vistos y los
vuelve a leer de ahí aunque el listado ya no los muestre.

Lo que se prueba es cuándo se acuerda y cuándo se olvida, que es lo único que
puede envejecer mal: recordar de más significa republicar un ciclo cancelado.
"""
import sys
from datetime import date, timedelta

from scraper import CTBA_MEMORIA_DIAS, _ctba_eventos_pendientes

HOY = date(2026, 9, 1)
PORTABELLA = "https://complejoteatral.gob.ar/ver/Integral-Pere-Portabella"
IMAMURA = "https://complejoteatral.gob.ar/ver/Shohei-Imamura"

fallos = 0


def chequear(que, ok, detalle=None):
    global fallos
    print(f"  {'✅' if ok else '❌'} {que}")
    if not ok:
        fallos += 1
        if detalle is not None:
            print(f"     → {detalle}")


def ev(url, titulo):
    return {"title": titulo, "ticket_url": "https://entradasba/x", "ver_url": url}


def main() -> int:
    listado = [ev(IMAMURA, "Shohei Imamura, antropólogo del deseo")]

    print("el día que el ciclo se cae del listado")
    recordados = {PORTABELLA: {"titulo": "Integral Pere Portabella",
                               "ticket_url": "https://entradasba/p",
                               "visto": (HOY - timedelta(days=1)).isoformat()}}
    pend = _ctba_eventos_pendientes(listado, recordados, HOY)
    chequear("el ciclo que salió del listado se relee igual",
             [p["ver_url"] for p in pend] == [PORTABELLA], pend)
    chequear("el que sigue en el listado no se relee dos veces",
             IMAMURA not in {p["ver_url"] for p in pend})
    chequear("y el del listado queda anotado con la fecha de hoy",
             recordados[IMAMURA]["visto"] == HOY.isoformat())

    print("\ncuándo se olvida")
    viejo = {PORTABELLA: {"titulo": "x", "ticket_url": "",
                          "visto": (HOY - timedelta(days=CTBA_MEMORIA_DIAS + 1)).isoformat()}}
    chequear(f"después de {CTBA_MEMORIA_DIAS} días sin aparecer, no se relee más",
             _ctba_eventos_pendientes(listado, viejo, HOY) == [])
    borde = {PORTABELLA: {"titulo": "x", "ticket_url": "",
                          "visto": (HOY - timedelta(days=CTBA_MEMORIA_DIAS)).isoformat()}}
    chequear("justo en el límite todavía se relee",
             len(_ctba_eventos_pendientes(listado, borde, HOY)) == 1)

    print("\nbasura en el archivo")
    for basura in ({PORTABELLA: {"visto": "ayer"}},
                   {PORTABELLA: {}},
                   {PORTABELLA: "no soy un dict"},
                   {PORTABELLA: {"visto": (HOY + timedelta(days=3)).isoformat()}}):
        chequear(f"una entrada inservible no rompe ni revive nada: {str(basura)[:52]}",
                 _ctba_eventos_pendientes(listado, dict(basura), HOY) == [])

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
