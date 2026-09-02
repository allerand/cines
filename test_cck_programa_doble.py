#!/usr/bin/env python3
"""
Test del parseo de la agenda del CCK contra el texto real de un evento, sin red.

    python3 test_cck_programa_doble.py

El caso: el CCK arma programas dobles y les cuelga las actividades en la misma
línea de horario:

    15 h: El chico en llamas + Tres tiempos + charlas con Alejo Santos y
          Natacha Valerga

Eso entraba a la cartelera como UNA función con ese título entero. Además de
leerse mal, se lleva puesta la ficha completa: un título compuesto no matchea
contra el bloque "Programación" del propio evento ni contra Letterboxd, así que
la fila salía sin director, sin año, sin duración y sin link — mientras que
"Romería", que va sola en su horario, salía completa. Era visible en la grilla
del domingo 6/9.

El fixture es el texto publicado de /events/cortar-y-contar/.
"""
import re
import sys
from datetime import date
from pathlib import Path

from scraper import (_CCK_SLOT_RE, _cck_fichas, _cck_ficha_programacion,
                     _cck_norm, _cck_split_titulos)

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "cck_cortar_y_contar.txt"

# La descripción llega desde JSON-LD y el scraper la colapsa a una línea. El
# test la normaliza igual, porque justamente ahí se perdía el separador que
# antes partía los programas dobles.
TEXTO = re.sub(r"\s+", " ", FIXTURE.read_text(encoding="utf-8"))

ESPERADO = {
    ("2026-09-04", "19:00"): [
        ("Desde el principio hasta el final", "Loana Pagani", 2023, 17),
        ("El sonido de antes", "Yael Szmulewicz", 2024, 74),
    ],
    ("2026-09-05", "16:00"): [
        ("Cómo ser Pehuén Pedre", "Federico Luis Tachella", 2024, 22),
        ("Cuando las nubes esconden la sombra", "José Luis Torres Leiva", 2024, 71),
    ],
    ("2026-09-05", "18:30"): [
        ("Sacrificio", "Joaquín Cazenave", 2025, 17),
        ("A Simple Soldier", "Juan Camilo Cruz y Artem Ryzhykov", 2025, 96),
    ],
    ("2026-09-06", "15:00"): [
        ("El chico en llamas", "Tadeo Martinez", 2024, 13),
        ("Tres tiempos", "Marlene Grinberg", 2025, 100),
    ],
    ("2026-09-06", "17:30"): [
        ("Romería", "Carla Simon", 2025, 115),
    ],
}


def main() -> int:
    fallos = 0

    def chequear(desc, ok, detalle=""):
        nonlocal fallos
        print(f"{'ok ' if ok else 'MAL'} {desc}" + (f"  → {detalle}" if not ok else ""))
        if not ok:
            fallos += 1

    # --- 1. El corte del slot -------------------------------------------------
    slot = ("El chico en llamas + Tres tiempos + charlas con Alejo Santos y "
            "Natacha Valerga")
    got = _cck_split_titulos(slot)
    chequear("un programa doble se parte en dos películas",
             got == ["El chico en llamas", "Tres tiempos"], got)

    chequear("un título solo queda intacto",
             _cck_split_titulos("Romería") == ["Romería"],
             _cck_split_titulos("Romería"))

    chequear("las charlas no entran como función",
             all("charla" not in t.lower() for t in got), got)

    # Un '+' pegado a las letras no es un separador de programa: sin espacios
    # alrededor se deja quieto, por si forma parte del título.
    chequear("un '+' pegado no parte el título",
             _cck_split_titulos("Blade Runner 2049+") == ["Blade Runner 2049+"],
             _cck_split_titulos("Blade Runner 2049+"))

    # La sala pegada al final del título hace el mismo daño que un programa
    # doble sin partir: el título deja de matchear y la ficha queda vacía.
    # Visto en la cartelera del 13/9: «Deuses de pedra Sala Manuel Antin».
    casos_sala = [
        ("Deuses de pedra Sala Manuel Antin", "Deuses de pedra"),
        ("La princesa de Francia Auditorio 511", "La princesa de Francia"),
        ("Romería", "Romería"),                       # sin sala, intacto
        ("El silencio antes de Bach", "El silencio antes de Bach"),
        # Minúscula: no es un nombre de sala, no se toca.
        ("Una tarde en la sala de espera", "Una tarde en la sala de espera"),
    ]
    for entrada, esperado in casos_sala:
        got = _cck_split_titulos(entrada)
        chequear(f"sala al final: «{entrada[:34]}»", got == [esperado], got)

    # --- 2. La ficha de cada película ----------------------------------------
    fichas_ciclo = _cck_fichas(TEXTO)
    chequear("la enumeración 'La programación incluye N títulos' se lee",
             len(fichas_ciclo) == 9, f"{len(fichas_ciclo)} títulos: {sorted(fichas_ciclo)[:3]}")

    for (fecha, hora), pelis in sorted(ESPERADO.items()):
        for titulo, director, anio, dur in pelis:
            ficha = _cck_ficha_programacion(TEXTO, titulo)
            if not ficha:
                ficha = dict(fichas_ciclo.get(_cck_norm(titulo), {}))
            ok = (ficha.get("director") == director and ficha.get("year") == anio
                  and ficha.get("duration") == dur)
            chequear(f"ficha de «{titulo}»", ok,
                     f"esperaba {director}/{anio}/{dur}′, salió {ficha or 'nada'}")

    # --- 3. Ninguna película se pierde ni se repite ---------------------------
    esperadas = {t for pelis in ESPERADO.values() for t, *_ in pelis}
    # Con el MISMO regex de slots que usa el scraper, no uno inventado acá.
    agenda = TEXTO[TEXTO.find("Agenda"):TEXTO.find("Las proyecciones")]
    todas = []
    for m in _CCK_SLOT_RE.finditer(agenda):
        todas.extend(_cck_split_titulos(m.group(3).strip(" -–:.,;")))
    chequear("las nueve películas del festival salen, sin repetir",
             len(todas) == 9 and {t.lower() for t in todas} == {e.lower() for e in esperadas},
             f"{len(todas)}: {todas}")

    # --- 4. scrape_cck completo, contra una página armada con este texto -----
    # Sin red: se sustituye la bajada y se ejercita el scraper de verdad —
    # secciones por fecha, slots, corte de títulos, ficha y Screening final.
    import html as _html
    import json as _json
    import scraper
    from bs4 import BeautifulSoup

    ev_url = "https://palaciolibertad.gob.ar/events/cortar-y-contar/"
    descripcion = "".join(f"<p>{_html.escape(l)}</p>"
                          for l in FIXTURE.read_text(encoding="utf-8").splitlines() if l.strip())
    ld = _json.dumps({"@type": "Event", "startDate": "2026-09-04T19:00:00",
                      "endDate": "2026-09-06T23:00:00", "description": descripcion})
    paginas = {
        "https://palaciolibertad.gob.ar/cine/": f'<a href="{ev_url}">Cortar y Contar</a>',
        ev_url: f'<h1>Cortar y Contar</h1>'
                f'<script type="application/ld+json">{ld}</script>',
    }
    # La caché de eventos (data/cck_eventos.json) guarda funciones YA PARSEADAS,
    # así que con la caché caliente este test mediría el parser viejo y daría
    # verde sin ejercitar nada. Se apunta a un archivo que no existe.
    import tempfile
    orig = scraper.fetch_html_cf
    orig_cache = scraper.CCK_CACHE_PATH
    scraper.CCK_CACHE_PATH = Path(tempfile.mkdtemp()) / "cck_eventos.json"
    scraper.fetch_html_cf = lambda url, ctx="": BeautifulSoup(paginas.get(url, ""), "html.parser")
    try:
        # La ventana tiene que alcanzar al festival (4-6/9) desde hoy.
        semanas = max(2, (date(2026, 9, 6) - date.today()).days // 7 + 1)
        funcs = scraper.scrape_cck(semanas=semanas)
    finally:
        scraper.fetch_html_cf = orig
        scraper.CCK_CACHE_PATH = orig_cache

    porslot = {}
    for f in funcs:
        porslot.setdefault((f.fecha, f.hora), []).append(f)

    vigentes = {k: v for k, v in ESPERADO.items() if k[0] >= date.today().isoformat()}
    chequear("scrape_cck devuelve un slot por horario del festival",
             set(porslot) == set(vigentes),
             f"salieron {sorted(porslot)} · esperaba {sorted(vigentes)}")

    for slot_key, pelis in sorted(vigentes.items()):
        got = sorted(f.title for f in porslot.get(slot_key, []))
        chequear(f"{slot_key[0]} {slot_key[1]}: una fila por película",
                 got == sorted(t for t, *_ in pelis), got)

    todas_f = [f for fs in porslot.values() for f in fs]
    sin_director = [f.title for f in todas_f if not f.director]
    chequear("ninguna función queda sin director", not sin_director, sin_director)
    sin_anio = [f.title for f in todas_f if not f.year]
    chequear("ninguna función queda sin año", not sin_anio, sin_anio)
    chequear("todas llevan el ciclo, que es lo que evita la alarma de "
             "'dos títulos en el mismo horario'",
             all(f.ciclo == "Cortar y Contar" for f in todas_f),
             {f.ciclo for f in todas_f})

    # La regla de calidad de la auditoría no tiene que quejarse de los
    # programas dobles: son dos películas en una función, a propósito.
    sys.path.insert(0, str(Path(__file__).parent / "scripts"))
    import audit
    rep = audit.Report()
    audit.check_calidad(rep, [{"cine": f.cine, "fecha": f.fecha, "hora": f.hora,
                               "title_es": f.title, "ciclo": f.ciclo,
                               "director": f.director, "year": f.year,
                               "ticket_url": f.ticket_url} for f in todas_f],
                        date.today())
    ruido = [m for _, m in rep.accion if "mismo horario" in m] + \
            [c for c in rep.cronico if "mismo horario" in c]
    chequear("la auditoría no marca los programas dobles como error", not ruido, ruido)

    # --- 5. La caché no puede servir salida de un parser viejo ---------------
    # Es la trampa que se comió este mismo arreglo: la caché guarda funciones ya
    # parseadas, así que arreglar el parser no la invalida y la cartelera sigue
    # publicando lo viejo hasta que expire sola. Peor, con la caché caliente el
    # fix parece no hacer nada y lo que se mide es el código anterior.
    from datetime import datetime
    entrada_vieja = {ev_url: {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "v": scraper.CCK_PARSER_VERSION - 1,
        "semanas": 99,
        "funciones": [{"cine": "CCK", "title": "A + B + charlas con Fulano",
                       "fecha": "2026-09-06", "hora": "15:00"}],
    }}
    chequear("una entrada de caché de otra versión del parser se descarta",
             scraper._cck_cache_get(entrada_vieja, ev_url, 2,
                                    date(2026, 9, 1), date(2026, 12, 1)) is None)
    entrada_vieja[ev_url]["v"] = scraper.CCK_PARSER_VERSION
    chequear("...y con la versión actual sí se usa",
             scraper._cck_cache_get(entrada_vieja, ev_url, 2,
                                    date(2026, 9, 1), date(2026, 12, 1)) is not None)

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
