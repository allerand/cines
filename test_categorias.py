#!/usr/bin/env python3
"""
Test local de categorias.py (el reglamento de qué va en cada casillero), sin
red ni git:

    python3 test_categorias.py

Los casos son los que aparecieron en la cartelera de verdad. Cada uno es un
dato que estaba en el casillero de otro y que nadie había visto:

  - La Sala Lugones del 15/11/2026 publicó "Homenaje a John Huston" como si
    fuera una película: el scraper no pudo leer el programa del ciclo.
  - El Borges pega el ciclo adelante del título («Ciclo Cuadro a Cuadro:
    Ánima Buenos Aires», «Ingmar Bergman: seis ensayos. PERSONA»).
  - Filo publica el género en la columna Ciclo ("Documental") y Amorina el
    tipo de actividad ("Cine"), y entre sus películas hay un torneo de ajedrez.
  - El 25 de Mayo y el MALBA pegan al director («…de Clarisa Navas»).
  - Sala Equis escribe «Festival Rizoma-calada».

Y los que NO tienen que saltar, que es lo que hace que el informe se lea:
una retrospectiva que se llama como su director, una sesión de festival
cargada a mano sin lista de películas, un título que termina en «de Algo».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import categorias as cat                                # noqa: E402

fallos = 0


def chequear(desc, ok, detalle=""):
    global fallos
    print(f"{'ok ' if ok else 'MAL'} {desc}" + (f" → {detalle}" if not ok else ""))
    if not ok:
        fallos += 1


def fila(titulo, cine="Sala X", ciclo="", director="", hora="18:00", fecha="2026-11-20", **kw):
    base = {"cine": cine, "fecha": fecha, "hora": hora, "title_es": titulo,
            "director": director, "ciclo": ciclo, "letterboxd": "", "year": None,
            "duration": None}
    base.update(kw)
    return base


def reglas(filas, **kw):
    return {(m.regla, m.cine) for m in cat.revisar(filas, **kw)}


def marca(regla, filas, **kw):
    return any(r == regla for r, _ in reglas(filas, **kw))


HUSTON = [fila("El halcón maltés", "Sala Lugones", "Homenaje a John Huston", "John Huston"),
          fila("La reina africana", "Sala Lugones", "Homenaje a John Huston", "John Huston", "21:00")]

# ── El título ─────────────────────────────────────────────────────────────
mala = fila("Homenaje a John Huston", "Sala Lugones", "Estreno", hora="15:00")
chequear("un título que es el nombre de un ciclo de su sala",
         marca("titulo-es-ciclo", HUSTON + [mala]))
chequear("...aunque las películas del ciclo sólo estén en la corrida anterior",
         marca("titulo-es-ciclo", [mala], previas=HUSTON))
chequear("...pero no el ciclo de otra sala",
         not marca("titulo-es-ciclo", HUSTON + [fila("Homenaje a John Huston", "Otra sala", "Estreno")]))
chequear("...ni un ciclo de una sola película que se llama como ella",
         not marca("titulo-es-ciclo", [fila("Nueve Auras", ciclo="Nueve Auras")]))
chequear("...ni una maratón que se llama como su ciclo",
         not marca("titulo-es-ciclo", [fila("Trilogía Pusher", ciclo="Trilogía Pusher"),
                                       fila("Pusher", ciclo="Trilogía Pusher", hora="20:00")]))

FEST = [{"slug": "bogota", "nombre": "Festival de Cine Experimental de Bogotá",
         "ciclo": "Festival de Cine Experimental de Bogotá",
         "alias": ["Festival de Cine Experimental de Bogotá", "CineAutopsia"]},
        {"slug": "mdq", "nombre": "Festival de Mar del Plata", "archivo": "data/x.json",
         "sedes": {"Aldrey 1": "Sarmiento 2685"}}]
chequear("un título que es el nombre de un festival del registro",
         marca("titulo-es-festival",
               [fila("Festival de Cine Experimental de Bogotá", "Centro Cultural Borges",
                     director="CineAutopsia")], festivales=FEST))
chequear("un título que nombra al festival cuando el ciclo no",
         marca("titulo-con-festival", [fila("Diciembre - CineAutopsia", "Cacodelphia")],
               festivales=FEST))
chequear("...y no si el ciclo ya es el del festival",
         not marca("titulo-con-festival",
                   [fila("Lo mejor de CineAutopsia", ciclo="Festival de Cine Experimental de Bogotá")],
                   festivales=FEST))

for titulo in ("Ciclo Cuadro a Cuadro: Ánima Buenos Aires",
               "Ciclo de Cine Peruano: Manco Cápac",
               "16º Festival Márgenes: Biografía de Jorge Luis Borges",
               "XXVII Ciclo de cine foro: Ellas en la ciudad"):
    chequear(f"el ciclo pegado adelante: {titulo}", marca("titulo-con-ciclo", [fila(titulo)]))

bergman = [fila(f"Ingmar Bergman: seis ensayos. {t}", "Centro Cultural Borges", hora=h)
           for t, h in (("PERSONA", "17:00"), ("SONATA DE OTOÑO", "19:00"), ("GRITOS Y SUSURROS", "21:00"))]
chequear("un prefijo que comparten tres títulos de la sala es un ciclo pegado",
         marca("titulo-con-ciclo", bergman))
chequear("...con dos no alcanza", not marca("titulo-con-ciclo", bergman[:2]))
equis = [fila(f"Festival Rizoma-{t}", "Sala Equis", hora=h, director="Alguien")
         for t, h in (("calada", "17:00"), ("cherri", "19:00"), ("muchedumbre", "21:00"))]
chequear("el guion sin espacios de Sala Equis también", marca("titulo-con-ciclo", equis))
saga = [fila(f"El Señor de los Anillos: {t}", "Hoyts Abasto", hora=h, director="Peter Jackson")
        for t, h in (("La comunidad del anillo", "14:00"), ("Las dos torres", "18:00"),
                     ("El retorno del rey", "22:00"))]
chequear("una saga en una cadena no es un ciclo pegado", not marca("titulo-con-ciclo", saga))
chequear("Spider-Man y X-Men no tienen prefijo",
         not marca("titulo-con-ciclo", [fila("Spider-Man: Brand New Day", hora="16:00"),
                                        fila("Spider-Man: No Way Home", hora="18:00"),
                                        fila("Spider-Man: Homecoming", hora="20:00")]))

chequear("un título que parece un ciclo y no tiene ficha",
         marca("titulo-parece-ciclo",
               [fila("Semana de los Festivales de Cine de Málaga y San Sebastián en Buenos Aires")]))
chequear("...no salta si tiene director",
         not marca("titulo-parece-ciclo", [fila("Foco Julio Fermepin", director="Julio Fermepin")]))
chequear("...ni «Encuentro con un Buda», que es una película",
         not marca("titulo-parece-ciclo", [fila("Encuentro con un Buda")]))

chequear("el director pegado con coma",
         marca("titulo-con-director",
               [fila("¿Qué clase de joven le abre la puerta a un vampiro?, de Boom Boom Kid y Zurita")]))
chequear("el director pegado después de un paréntesis",
         marca("titulo-con-director",
               [fila("Encuentro con un Buda (Meeting the Buddha) de Marta György-Kessler")]))
chequear("«X de Nombre Apellido» se confirma si otra sala tiene X con ese director",
         marca("titulo-con-director",
               [fila("El príncipe de Nanawa de Clarisa Navas", "Centro Cultural 25 de Mayo"),
                fila("El príncipe de Nanawa", "Filo Cine", director="Clarisa Navas")]))
chequear("...sin confirmar y con año, queda como duda",
         marca("titulo-quizas-con-director", [fila("El príncipe de Nanawa de Clarisa Navas", year=2025)]))
chequear("...sin confirmar y sin ningún dato, no se dice nada",
         not {r for r, _ in reglas([fila("Lo Queer en el Cine de Oro Argentino"),
                                    fila("ALIENTO - 10 años del Programa de Cine UTDT", hora="20:00")])}
         & {"titulo-con-director", "titulo-quizas-con-director"})
chequear("«El secreto de Vera Drake» con su director no molesta",
         not {r for r, _ in reglas([fila("El secreto de Vera Drake", director="Mike Leigh")])}
         & {"titulo-con-director", "titulo-quizas-con-director"})
chequear("director_en_titulo corta bien el de la derecha",
         cat.director_en_titulo("El príncipe de Nanawa de Clarisa Navas")
         == ("El príncipe de Nanawa", "Clarisa Navas", False))

chequear("un torneo de ajedrez no es una película",
         marca("titulo-no-es-pelicula", [fila("Torneo de ajedrez", "Amorina")]))
chequear("un ballet en vivo tampoco",
         marca("titulo-no-es-pelicula", [fila("El Cascanueces- Ballet Live Roh 26-27", "Cines Ideal")]))
chequear("...pero «Ballet 422», con su ficha, sí",
         not marca("titulo-no-es-pelicula",
                   [fila("Ballet 422", director="Jody Lee Lipes", letterboxd="https://x/")]))
chequear("la versión pegada al título",
         marca("titulo-con-etiqueta", [fila("CINCO SEGUNDOS V.O.S.E. Sesión Teta", "Artistic Metropol")]))
chequear("un tramo en mayúsculas",
         marca("titulo-gritado", [fila("RECEN POR MÍ: La historia de Francisco")]))
chequear("...y no un número romano ni una sigla suelta",
         not marca("titulo-gritado", [fila("Rocky IV"), fila("TÁR", hora="20:00"),
                                      fila("Pusher III: Soy el ángel de la muerte", hora="22:00")]))

# ── El ciclo ──────────────────────────────────────────────────────────────
chequear("el género en la columna Ciclo", marca("ciclo-es-genero", [fila("Diciembre", "Filo Cine", "Documental")]))
chequear("el tipo de actividad en la columna Ciclo", marca("ciclo-es-tipo", [fila("Taxi Driver", "Amorina", "Cine")]))
chequear("«Estreno» y «Continúa» son etiquetas y se quedan",
         not {r for r, _ in reglas([fila("Perfume", "MALBA", "Estreno"),
                                    fila("Annemarie", "MALBA", "Continúa", hora="20:00")])})
chequear("un ciclo con una palabra gritada", marca("ciclo-gritado", [fila("Eika Katappa", ciclo="CINE en 16mm")]))
chequear("...una sigla no es un grito", not marca("ciclo-gritado", [fila("Elton", ciclo="Festival FIDBA - Órbita")]))
chequear("el ciclo con la puntuación rota",
         marca("ciclo-mal-escrito", [fila("El jockey", ciclo="Miradas contemporáneas:Luis Ortega / Federico Luis")]))
chequear("...una hora o un número con dos puntos no la rompen",
         not marca("ciclo-mal-escrito", [fila("X", ciclo="Trasnoche de las 23:30")]))
chequear("el mismo ciclo escrito de dos maneras",
         marca("ciclo-escrito-distinto",
               [fila("A", ciclo="Ruido y Furia . 50 Años de Punk"),
                fila("B", ciclo="Ruido y Furia. 50 Años de Punk", hora="20:00"),
                fila("C", ciclo="Ruido y Furia. 50 Años de Punk", hora="22:00", cine="Otra")]))

# ── El director ───────────────────────────────────────────────────────────
chequear("una retrospectiva que se llama como su director no es una mezcla",
         not marca("director-es-otra-cosa", [fila("Eight Bridges", "Cine Doré", "James Benning", "James Benning")]))
chequear("el título en el lugar del director",
         marca("director-es-otra-cosa", [fila("Persona", director="Persona")]))
chequear("un director de relleno", marca("director-relleno", [fila("Película sorpresa", director="Desconocido")]))
chequear("la ficha entera en el director",
         marca("director-con-numeros", [fila("Nuestra Juventud", director="Roland Steiner. RDA. 1989. 88 min")]))

# ── La sala ───────────────────────────────────────────────────────────────
SALAS = {"MALBA": "ba", "Cine Doré": "madrid"}
chequear("una sala que la web no conoce",
         marca("sala-desconocida", [fila("X", "Sala Nueva")], salas=SALAS, ciudad="ba"))
chequear("una sala de Madrid en la cartelera de Buenos Aires",
         marca("sala-de-otra-ciudad", [fila("X", "Cine Doré")], salas=SALAS, ciudad="ba"))
chequear("las cadenas no están en el padrón sala por sala",
         not marca("sala-desconocida", [fila("X", "Hoyts Abasto")], salas=SALAS, ciudad="ba"))
chequear("un festival de afuera adentro de la cartelera",
         marca("festival-de-afuera-adentro", [fila("X", "Aldrey 1")], festivales=FEST, ciudad="ba"))

# ── A mano, excepciones y cuentas ─────────────────────────────────────────
sesion = fila("Competencia Internacional", "Universidad del Cine",
              "Infinito Super 8 - Competencia Internacional")
chequear("una sesión de festival sin lista de películas salta...",
         marca("titulo-parece-ciclo", [sesion]))
chequear("...salvo que esté cargada a mano",
         not marca("titulo-parece-ciclo", [sesion], a_mano={cat.clave_a_mano(sesion)}))
chequear("una excepción la saca del informe",
         not marca("titulo-no-es-pelicula", [fila("Torneo de ajedrez", "Amorina")],
                   excepcion=lambda regla, cine, valor, f: regla == "titulo-no-es-pelicula"))
docs = [fila(f"Peli {i}", "Filo Cine", "Documental", hora=f"{10 + i}:00") for i in range(8)]
m = [x for x in cat.revisar(docs) if x.regla == "ciclo-es-genero"]
chequear("una mezcla por dato, con la cuenta de funciones", len(m) == 1 and m[0].n == 8, str(m))

# ── El portero ────────────────────────────────────────────────────────────
quedan, ret = cat.portero(HUSTON + [mala])
chequear("el portero frena el ciclo puesto como película y deja las películas",
         len(quedan) == 2 and [r["title_es"] for r in ret] == ["Homenaje a John Huston"]
         and ret[0]["regla"] == "titulo-es-ciclo" and "no una película" in ret[0]["motivo"], str(ret))
quedan, ret = cat.portero([mala], previas=HUSTON)
chequear("...también cuando las películas sólo estaban en la corrida anterior",
         not quedan and len(ret) == 1)
quedan, ret = cat.portero(HUSTON + [mala], a_mano={cat.clave_a_mano(mala)})
chequear("...pero no toca lo cargado a mano", len(quedan) == 3 and not ret)
borges = fila("Festival de Cine Experimental de Bogotá", "Centro Cultural Borges", director="CineAutopsia")
_, ret = cat.portero([borges], festivales=FEST)
chequear("frena un título que es un festival del registro", len(ret) == 1)
_, ret = cat.portero([dict(borges, cine="Cine Doré")], festivales=FEST, sin_registro={"Cine Doré"})
chequear("...y no en Madrid, donde el registro no aplica", not ret)
dudosas = [fila("Ciclo Cuadro a Cuadro: Ánima Buenos Aires"), fila("Torneo de ajedrez", hora="20:00"),
           fila("Semana de los Festivales de Cine de Málaga", hora="22:00")]
quedan, ret = cat.portero(dudosas)
chequear("lo dudoso no lo frena: eso es para la auditoría", len(quedan) == 3 and not ret)
chequear("el portero no cambia las filas que deja pasar", quedan[0] is dudosas[0])

# ── El portero, tal como lo llama run.py ──────────────────────────────────
# Se corre el bloque de verdad, sacado del fuente (importar run.py arranca
# playwright), con un scraper de mentira y la cartelera anterior en un
# archivo temporal.
import contextlib                                       # noqa: E402
import io                                               # noqa: E402
import json                                             # noqa: E402
import tempfile                                         # noqa: E402
import textwrap                                         # noqa: E402
import types                                            # noqa: E402

fuente = (Path(__file__).parent / "run.py").read_text(encoding="utf-8")
bloque = textwrap.dedent(fuente[fuente.index("    retenidas: list = []"):
                                fuente.index("    # Procedencia por cine")])


def correr_bloque(filas, festivales):
    with tempfile.TemporaryDirectory() as tmp:
        anterior = Path(tmp) / "cartelera.json"
        anterior.write_text(json.dumps({"screenings": HUSTON}), encoding="utf-8")
        falso = types.ModuleType("scraper")
        falso._load_manual = lambda: {"screenings": [
            {"cine": "Sala Lugones", "fecha": "2026-11-20", "hora": "23:00", "title": "Homenaje a John Huston"}]}
        falso._cargar_festivales = festivales
        real = sys.modules.get("scraper")
        sys.modules["scraper"] = falso
        ns = {"json": json, "screenings_out": list(filas), "CARTELERA_JSON": anterior,
              "CARTELERA_MADRID_JSON": Path(tmp) / "no-existe.json", "CINES_MADRID": {"Cine Doré"}}
        try:
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                exec(bloque, ns)
        finally:
            if real is None:
                del sys.modules["scraper"]
            else:
                sys.modules["scraper"] = real
        return ns, salida.getvalue()


a_mano = dict(mala, hora="23:00")
otra = fila("Otra película", "Sala Lugones", hora="22:00", director="Alguien")
dore = dict(borges, cine="Cine Doré")
ns, log = correr_bloque([mala, a_mano, borges, dore, otra], lambda: FEST)
chequear("en run.py: frena el ciclo (lo conoce por la corrida anterior) y el festival",
         [(r["cine"], r["regla"]) for r in ns["retenidas"]]
         == [("Sala Lugones", "titulo-es-ciclo"), ("Centro Cultural Borges", "titulo-es-festival")],
         str(ns["retenidas"]))
chequear("...deja lo cargado a mano, lo de Madrid y las películas, en su orden",
         ns["screenings_out"] == [a_mano, dore, otra], str(ns["screenings_out"]))
chequear("...lo dice en el log del scrape y no reporta falla",
         log.count("Portero: no se publica") == 2 and ns["portero_dice"] == "", log)


def se_cae():
    raise RuntimeError("festivales.json ilegible")


ns, log = correr_bloque([mala, otra], se_cae)
chequear("si el portero se cae, se publica como siempre y queda dicho para la auditoría",
         ns["screenings_out"] == [mala, otra] and ns["retenidas"] == []
         and "festivales.json ilegible" in ns["portero_dice"] and "Portero omitido" in log,
         f"{ns['portero_dice']} | {log}")

print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
raise SystemExit(1 if fallos else 0)
