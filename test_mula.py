#!/usr/bin/env python3
"""
Test local del scraper de La Mula Club de Cine (su sitio en Passline), sin red:

    python3 test_mula.py

La tarjeta es la real de la página que Mateo guardó desde su Chrome el
18/11/2026, recortada. Passline le contesta 403 (control anti-bots de
Cloudflare) a cualquier pedido que no venga de un navegador: el parser está
probado, la bajada no anda, y scrape_mula lo tiene que decir.
"""
import urllib.error
from datetime import date

import scraper
from scraper import _mula_funciones


def tarjeta(nombre, cuando, slug, lugar="Metauro Espacio Cultural"):
    return f"""
    <div class="col-md-3 col-sm-12 col-xs-12 masonry-item" style="position: absolute; left: 0px; top: 0px;">
        <a href="https://www.passline.com/sitio-evento/{slug}">
            <span class="thumb-info thumb-info-centered-info thumb-info-no-borders">
                <span class="thumb-info-wrapper">
                    <div style="z-index: 1;" class="corner-ribbon top-left yellow shadow"><strong>PROMO</strong></div>
                    <img src="https://www.passline.com/imagenes/eventos/-826229-rec.jpg" class="img-responsive">
                    <span class="thumb-info-title"><span class="thumb-info-type"><i class="fa fa-ticket"></i>
                        Comprar </span></span>
                </span>
            </span>
        </a>
        <div class="p-lg border-bottom descripcion-evento">
            <span class="h4" title="{nombre}">
                {nombre}                                                    </span>
            <ul class="list list-icons list-primary list-borders" style="margin-bottom: 0 !important;">
                <li class="fecha-site" style="height:53px;"><i class="fa fa-calendar"></i>

                    {cuando}                                                            </li>
                <li class="lugar-site"><i class="fa fa-map-marker"></i>
                    <div style="overflow: hidden;">
                        {lugar}                                                            </div>
                </li>
            </ul>
        </div>
        <a href="https://www.passline.com/sitio-evento/{slug}" class="btn btn-primary btn-lg mr-xs mb-sm btn-w">
            <i class="fa fa-ticket" aria-hidden="true"></i>
            Comprar                                                </a>
    </div>"""


def pagina(*tarjetas):
    return ('<!DOCTYPE html><html><head><title>La Mula Club de Cine - Passline</title></head><body>'
            '<div class="row row-white-transparent mt-eventos-home"><div class="masonry">'
            + "".join(tarjetas) + '</div></div>'
            '<section id="maps"><h1>lamula.clubdecine@gmail.com</h1></section></body></html>')


CORTOS = tarjeta("Cortos en La Mula - 22/11 a las 18.30hs", "22 de Noviembre 2026 a las 18:30",
                 "cortos-en-la-mula-2211-a-las-1830hs")

# --- La tarjeta real ----------------------------------------------------------
[s] = _mula_funciones(pagina(CORTOS))
assert (s.cine, s.title, s.fecha, s.hora) == ("La Mula Club de Cine", "Cortos en La Mula", "2026-11-22", "18:30")
assert s.ticket_url == "https://www.passline.com/sitio-evento/cortos-en-la-mula-2211-a-las-1830hs"
assert (s.director, s.year) == ("", None)
print("✓ la tarjeta: nombre sin el día y la hora de atrás, fecha del renglón del calendario, link al evento")

# --- Otras formas del nombre y de la fecha -----------------------------------
varias = _mula_funciones(pagina(
    CORTOS,
    tarjeta("El espíritu de la colmena", "5 de Diciembre 2026 a las 20:00", "el-espiritu-de-la-colmena"),
    tarjeta("Stalker – 12/12", "12 de diciembre de 2026 a las 19.30", "stalker-1212"),
    tarjeta("Taller de cine en Super 8 - 13/12", "13 de Diciembre 2026 a las 15:00", "taller-super-8"),
    tarjeta("Abono 2027", "Del 1 de Marzo al 30 de Noviembre", "abono-2027"),
    tarjeta("Fecha imposible", "31 de Febrero 2027 a las 20:00", "x"),
    CORTOS,
))
assert [(s.title, s.fecha, s.hora) for s in varias] == [
    ("Cortos en La Mula", "2026-11-22", "18:30"),
    ("El espíritu de la colmena", "2026-12-05", "20:00"),
    ("Stalker", "2026-12-12", "19:30")], varias
print("✓ un nombre sin cola queda igual; un taller, un abono sin fecha sola, una fecha imposible y un repetido no salen")

assert _mula_funciones(pagina()) == []
assert _mula_funciones("<html><body>Just a moment...</body></html>") == []
print("✓ sin tarjetas no inventa nada")


# --- scrape_mula --------------------------------------------------------------
class _Hoy(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 18)


_date, _fetch = scraper.date, scraper.fetch_bytes
scraper.date = _Hoy
try:
    pedidas = []

    def _pagina(url, *a, **k):
        pedidas.append((url, k.get("intentos")))
        return pagina(CORTOS, tarjeta("Ya pasó - 1/11", "1 de Noviembre 2026 a las 18:30", "ya-paso")).encode("utf-8")
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = _pagina
    r = scraper.scrape_mula()
    assert [(s.title, s.fecha) for s in r] == [("Cortos en La Mula", "2026-11-22")]
    assert pedidas == [("https://www.passline.com/sitio/la-mula-club-de-cine-849412648", 1)]
    assert not scraper.FUENTES_CAIDAS
    print("✓ scrape_mula: con la página en la mano, lo que viene; pide una sola vez y sin parámetros de seguimiento")

    # Lo que pasa hoy: Passline contesta 403 con el desafío de Cloudflare.
    def _rechazo(url, *a, **k):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
    scraper.fetch_bytes = _rechazo
    assert scraper.scrape_mula() == []
    assert "HTTP 403" in scraper.FUENTES_CAIDAS["La Mula Club de Cine"]
    assert "anti-bots" in scraper.FUENTES_CAIDAS["La Mula Club de Cine"]
    print("✓ el 403 de Passline no da un cero mudo: queda dicho que es el control anti-bots")

    # El desafío también puede venir con 200 y su propio HTML.
    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: (b"<html><head><title>Just a moment...</title></head>"
                                                b"<body>Enable JavaScript and cookies to continue</body></html>")
    assert scraper.scrape_mula() == [] and "anti-bots" in scraper.FUENTES_CAIDAS["La Mula Club de Cine"]

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: b"<html><body><h1>Passline</h1></body></html>"
    assert scraper.scrape_mula() == [] and "cambi" in scraper.FUENTES_CAIDAS["La Mula Club de Cine"]

    scraper.FUENTES_CAIDAS.clear()
    scraper.fetch_bytes = lambda url, *a, **k: pagina().encode("utf-8")
    assert scraper.scrape_mula() == [] and not scraper.FUENTES_CAIDAS
    print("✓ el desafío con 200 y un cambio de armado se avisan; una página sin eventos no es una caída")
finally:
    scraper.date, scraper.fetch_bytes = _date, _fetch
    scraper.FUENTES_CAIDAS.clear()

print("\nTodo OK")
