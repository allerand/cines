#!/usr/bin/env python3
"""
Test del parseo de las fichas de Sala Lúcida contra HTML real, sin red.

    python3 test_sala_lucida.py

Los fixtures son el <main> de cuatro fichas de portal.salalucida.org, elegidas
porque cubren las cuatro formas en que la sala escribe una función:

  · tierra_citrus   — el caso simple: h2 "CINE", el título en un h3 y
                      "Dir: Fulana (65 min)" abajo.
  · matria          — igual, pero con un h3 "ESTRENOS" en el medio: el título
                      es el encabezado MÁS CERCANO al "Dir:", no el primero.
  · galeria_nocturna— ciclo con copete, subtítulo de parte y la duración
                      metida en el encabezado del título; el h2 del evento
                      viene con el ciclo de prefijo.
  · el_diablo       — el año en el encabezado ("(1984)") y el ciclo en el h2.

Lo que se está protegiendo es el título: la descripción lo escribe en
mayúsculas y muchas veces sin tildes ("UNA CANCION PARA MI TIERRA"), y con ese
título no hay match ni en TMDb ni en Letterboxd. El h2 del evento sí lo trae
bien escrito, y el parser tiene que preferirlo cuando son la misma película.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from scraper import _lucida_parse_evento, _lucida_fecha_hora

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
HOY = date(2026, 9, 1)
FIN = HOY + timedelta(weeks=9)

# fixture → (título, director, año, duración, ciclo, fecha, hora)
ESPERADO = {
    "sala_lucida_tierra_citrus": [
        ("Tierra Citrus", "Ayelen Agüero", None, 65, "", "2026-09-02", "20:00"),
    ],
    "sala_lucida_matria": [
        ("Matria", "Jimena Chavez", None, 75, "", "2026-09-03", "20:00"),
    ],
    "sala_lucida_galeria_nocturna": [
        ("Si muero antes de despertar", "Carlos Hugo Christensen", None, 73,
         "Galeria Nocturna", "2026-09-04", "22:00"),
    ],
    "sala_lucida_el_diablo": [
        ("El diablo nunca duerme", "Lourdes Portillo", 1984, 84,
         "Secretos Familiares", "2026-09-05", "16:00"),
    ],
}

fallos = 0


def chequear(que: str, ok: bool, detalle=None) -> None:
    global fallos
    print(f"  {'✅' if ok else '❌'} {que}")
    if not ok:
        fallos += 1
        if detalle is not None:
            print(f"     → {detalle}")


def main() -> int:
    print("Fechas")
    chequear('"2.SEP.2026 20:00hs"',
             _lucida_fecha_hora("2.SEP.2026 20:00hs") == (date(2026, 9, 2), "20:00"),
             _lucida_fecha_hora("2.SEP.2026 20:00hs"))
    chequear('"13.DIC.2026 9:30hs" (hora de un dígito)',
             _lucida_fecha_hora("13.DIC.2026 9:30hs") == (date(2026, 12, 13), "09:30"),
             _lucida_fecha_hora("13.DIC.2026 9:30hs"))
    chequear("un mes que no existe no inventa fecha",
             _lucida_fecha_hora("2.XXX.2026 20:00hs") == (None, ""))

    for nombre, esperado in ESPERADO.items():
        print(f"\n{nombre}")
        soup = BeautifulSoup((FIXTURES / f"{nombre}.html").read_text(encoding="utf-8"),
                             "html.parser")
        url = f"https://portal.salalucida.org/eventos/{nombre}"
        got = _lucida_parse_evento(soup, url, HOY, FIN)
        obtenido = [(s.title, s.director, s.year, s.duration, s.ciclo, s.fecha, s.hora)
                    for s in got]
        chequear(f"{len(esperado)} función(es) con la ficha completa",
                 obtenido == esperado, obtenido)
        chequear("todas apuntan al ticket del evento",
                 all(s.ticket_url == url and s.cine == "Sala Lúcida" for s in got))

    # Fuera de la ventana no entra nada: el portal publica con meses de
    # anticipación y la cartelera no muestra tan lejos.
    print("\nventana de fechas")
    soup = BeautifulSoup((FIXTURES / "sala_lucida_tierra_citrus.html").read_text(encoding="utf-8"),
                         "html.parser")
    chequear("una función anterior a hoy queda afuera",
             _lucida_parse_evento(soup, "u", date(2026, 9, 3), FIN) == [])
    chequear("una función más allá del corte queda afuera",
             _lucida_parse_evento(soup, "u", HOY, date(2026, 9, 1)) == [])

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
