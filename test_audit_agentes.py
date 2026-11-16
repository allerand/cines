#!/usr/bin/env python3
"""
Test local de la lógica de agentes de la auditoría (scripts/audit.py,
audit_fuentes.py y audit_festivales.py), sin red ni git:

    python3 test_audit_agentes.py

Cubre lo que se sumó el 16/11/2026 para que nada se pierda de una semana a la
otra. Cada caso es algo que ya pasó o una falsa alarma que salió al probarlo
contra la cartelera de verdad:

  - El CEA dejó de traer funciones el 17/10/2026 y un mes después ningún
    informe lo nombraba: llevaba caído más que la ventana de 14 días.
  - El Marechal salía "caído" al terminar el FESTIHUR.
  - El CCK y el Borges se ven en cero después del pase de la tarde, que los
    saltea a propósito.
  - Los Cines Ideal de Madrid, una semana con 30 preventas de diciembre y
    ninguna función para hoy; el Cine Estudio, que cierra los lunes, no.
  - Un hallazgo que sigue abierto no es una novedad cada lunes, y uno que se
    cierra hay que contarlo.
  - Un festival que empieza la semana que viene sin funciones cargadas, uno
    que cambió la grilla en su web, y uno que vuelve todos los años y no
    está en el registro.
"""
import json
import sys
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import audit                                            # noqa: E402
import audit_festivales as monitor                      # noqa: E402
from audit_fuentes import Historia, chispa, tablero     # noqa: E402

HOY = date(2026, 11, 16)          # lunes
fallos = 0


def chequear(desc, ok, detalle=""):
    global fallos
    print(f"{'ok ' if ok else 'MAL'} {desc}" + (f" → {detalle}" if not ok else ""))
    if not ok:
        fallos += 1


def dia(n: int) -> str:
    """El día de hace n días, en ISO."""
    return (HOY - timedelta(days=n)).isoformat()


def funcion(cine, fecha, hora="18:00", titulo="Peli", **kw):
    return dict({"cine": cine, "fecha": fecha, "hora": hora, "title_es": titulo,
                 "director": "Alguien", "ciclo": "", "letterboxd": "https://x/",
                 "ticket_url": "https://x/"}, **kw)


def historia(series: dict, fuentes: dict = None, ciclos: dict = None, adelante: int = 3) -> Historia:
    """{sala: [funciones hoy, ayer, anteayer…]} → una Historia como la que sale
    de git. Cada día, la sala tiene esas funciones repartidas en los `adelante`
    días siguientes. `fuentes`: {sala: [¿scrapeó? hoy, ayer…]}."""
    h = Historia()
    largo = max(len(v) for v in series.values())
    for i in range(largo - 1, -1, -1):
        d = dia(i)
        filas = []
        for sala, vals in series.items():
            n = vals[i] if i < len(vals) else 0
            for k in range(n):
                f = (date.fromisoformat(d) + timedelta(days=k % adelante)).isoformat()
                filas.append(funcion(sala, f, f"{10 + k % 12}:00", f"Peli {k}",
                                     ciclo=(ciclos or {}).get(sala, "")))
        payload = {"screenings": filas}
        if fuentes:
            payload["fuentes"] = {sala: {"scrapeadas": 5 if vivos[i] else 0, "publicadas": 5}
                                  for sala, vivos in fuentes.items() if i < len(vivos)}
        h.registrar(d, payload)
        h._payloads = getattr(h, "_payloads", {})
        h._payloads[d] = payload
    h.filas = lambda d: h._payloads.get(d, {}).get("screenings", [])
    return h


def cobertura(series, **kw):
    """check_cobertura con el historial largo y la ventana corta de siempre."""
    h = historia(series, kw.pop("vivas", None), kw.pop("ciclos", None))
    snaps = {d: h.funciones[d] for d in h.dias[-14:]}
    rep = audit.Report()
    audit.check_cobertura(rep, kw.pop("screenings", []), HOY, snaps, kw.pop("probes", {}),
                          kw.pop("fuentes", None), largo=h, sondas={}, **kw)
    return {c: m for c, m in rep.accion}, " ".join(rep.cronico)


# ── Salas apagadas: el historial largo ────────────────────────────────────
acc, _ = cobertura({"CEA": [0] * 30 + [3, 4, 2, 5, 3] * 12})
msg = acc.get("CEA", "")
chequear("una sala estable apagada hace un mes avisa, aunque la ventana corta ya no la vea",
         "30 días" in msg and "traía ~3 por día" in msg, msg or "sin aviso")

acc, cron = cobertura({"Sala Mario Soffici": [0] * 80 + [7] * 8})
chequear("una sala que apareció ocho días hace tres meses no es una caída",
         "Sala Mario Soffici" not in acc and "Sala Mario Soffici" not in cron, str(acc))

acc, cron = cobertura({"Centro Cultural Leopoldo Marechal": [0] * 8 + [51] * 8},
                      ciclos={"Centro Cultural Leopoldo Marechal": "FESTIHUR - Competencia"},
                      claves_festival=["festihur"])
chequear("una sala de festival en cero cuando terminó el festival no es una caída",
         "Centro Cultural Leopoldo Marechal" not in acc, str(acc))

acc, _ = cobertura({"Cine Gaumont": [0] * 3 + [30] * 30},
                   ciclos={"Cine Gaumont": ""}, claves_festival=["festihur"])
chequear("...pero una sala de siempre en cero sigue avisando", "Cine Gaumont" in acc, str(acc))

acc, cron = cobertura({"CEA": [0] * 10 + [3] * 60}, probes={"CEA": (0, "funciones anunciadas en la home")})
chequear("con la sonda en 0, diez días en cero se nombran sin gritar",
         "CEA" not in acc and "sonda tampoco" in cron, f"{acc} | {cron}")
acc, cron = cobertura({"CEA": [0] * 30 + [3] * 60}, probes={"CEA": (0, "funciones anunciadas en la home")})
chequear("...pero un mes en cero es para mirar aunque la sonda no vea nada (puede estar ciega)",
         "sonda tampoco" in acc.get("CEA", "") and "abrir su web" in acc.get("CEA", ""), f"{acc} | {cron}")

# ── Fuentes caídas: el pase de la tarde ───────────────────────────────────
borges = [funcion("Centro Cultural Borges", dia(-2), f"{15 + i}:00", f"Peli {i}") for i in range(4)]
caida = {"Centro Cultural Borges": {"scrapeadas": 0, "publicadas": 4}}
acc, _ = cobertura({"Centro Cultural Borges": [4] * 20}, screenings=borges, fuentes=caida,
                   vivas={"Centro Cultural Borges": [False, True, True, True, True, True, True, True]})
chequear("el Borges en cero sólo en la corrida de hoy (el pase de la tarde lo saltea) no avisa",
         "Centro Cultural Borges" not in acc, str(acc))
acc, _ = cobertura({"Centro Cultural Borges": [4] * 20}, screenings=borges, fuentes=caida,
                   vivas={"Centro Cultural Borges": [False, False, False, True, True, True, True, True]})
msg = acc.get("Centro Cultural Borges", "")
chequear("...y con tres días sin contestar avisa, y dice hace cuánto",
         "no contesta hace 3 días" in msg, msg or "sin aviso")
malba = [funcion("MALBA", dia(-2), f"{15 + i}:00", f"Peli {i}") for i in range(4)]
acc, _ = cobertura({"MALBA": [4] * 20}, screenings=malba,
                   fuentes={"MALBA": {"scrapeadas": 0, "publicadas": 4}},
                   vivas={"MALBA": [False, True, True, True, True, True, True, True]})
chequear("una sala que no va por el proxy avisa desde la primera corrida en cero",
         "no scrapeó ninguna" in acc.get("MALBA", ""), str(acc))

# ── El tablero y lo que el conteo no muestra ──────────────────────────────
def filas_tablero(series, hoy_filas, fuentes, **kw):
    h = historia(series, kw.pop("vivas", None), adelante=kw.pop("adelante", 3))
    return tablero(h, hoy_filas, fuentes, HOY, **kw)


def rendimiento(filas):
    rep = audit.Report()
    audit.check_rendimiento(rep, filas)
    return {c: m for c, m in rep.accion}, " ".join(rep.cronico)


lejanas = [funcion("Cines Ideal", dia(-20 - i), "20:00", f"Preventa {i}") for i in range(6)]
t = filas_tablero({"Cines Ideal": [6] + [40] * 34}, lejanas,
                  {"Cines Ideal": {"scrapeadas": 6, "publicadas": 6}})
acc, _ = rendimiento(t)
chequear("una sala de todos los días con funciones sólo lejanas avisa",
         "ninguna para hoy ni para mañana" in acc.get("Cines Ideal", ""), str(acc))

# Cierra lunes y martes: hoy es lunes y esos días nunca tuvo funciones.
h = Historia()
for i in range(34, -1, -1):
    d = date.fromisoformat(dia(i))
    abre = d.weekday() >= 2
    h.registrar(d.isoformat(), {"screenings": [
        funcion("Cine Estudio", (d + timedelta(days=k)).isoformat())
        for k in range(0 if abre else (2 - d.weekday()), 6)]})
proximas = [funcion("Cine Estudio", dia(-2 - i)) for i in range(5)]
t = tablero(h, proximas, {"Cine Estudio": {"scrapeadas": 5, "publicadas": 5}}, HOY)
acc, _ = rendimiento(t)
chequear("...una que cierra lunes y martes, un lunes, no", "Cine Estudio" not in acc, str(acc))
chequear("mismos_dias compara lunes con lunes", t[0]["mismos_dias"] == (0, 4, 0), str(t[0]["mismos_dias"]))

bcn = [funcion("Biblioteca del Congreso", dia(-3 - i)) for i in range(6)]
t = filas_tablero({"Biblioteca del Congreso": [6] + [3] * 34}, bcn,
                  {"Biblioteca del Congreso": {"scrapeadas": 6, "publicadas": 6}})
acc, _ = rendimiento(t)
chequear("...ni una sala chica que da una función por día y arranca el ciclo el miércoles",
         "Biblioteca del Congreso" not in acc, str(acc))

t = filas_tablero({"Cine York": [1] + [30] * 34},
                  [funcion("Cine York", dia(-1))],
                  {"Cine York": {"scrapeadas": 1, "publicadas": 1}}, adelante=12)
_, cron = rendimiento(t)
chequear("una sala que se queda sin programación mañana se nombra",
         "Se quedan sin programación" in cron and "Cine York" in cron, cron)

t = filas_tablero({"Casa del Bicentenario": [9] * 20},
                  [funcion("Casa del Bicentenario", dia(-1))],
                  {"Casa del Bicentenario": {"scrapeadas": 1, "publicadas": 1}},
                  vivas={"Casa del Bicentenario": [True, False, False, True, False, False, False]})
_, cron = rendimiento(t)
chequear("una fuente que contesta dos de siete días se nombra", "2 de los últimos 7" in cron, cron)

chequear("la barrita marca los días en cero y va a escala de la sala",
         chispa([0, 1, 5, 10, 0]) == "_▂▅█_", chispa([0, 1, 5, 10, 0]))
chequear("una fecha que no es una fecha no rompe el historial",
         bool(historia({"Sala Lugones": [3] * 5}).registrar(
             dia(0), {"screenings": [funcion("Sala Lugones", "Sin fecha")]}) is None))

# ── La memoria: nuevo, sigue abierto, resuelto ────────────────────────────
def informe(hallazgos):
    rep = audit.Report()
    for sev, cine, regla, msg in hallazgos:
        (rep.accionar if sev == "E" else lambda c, m, regla: rep.cronicar(m, cine=c, regla=regla))(
            cine, msg, regla=regla)
    return rep


CAIDO = ("E", "CEA", "caido", "lleva 30 días sin ninguna función")
MEZCLA = ("E", "Amorina", "titulo-no-es-pelicula", "hay actividades que no son películas")

rep = informe([CAIDO])
estado, estrenan = audit.fechar(rep, None, HOY)
chequear("sin informe anterior todo es nuevo y no hay memoria",
         rep.hallazgos[0].nuevo and not rep.con_memoria and len(estrenan) == 1)
chequear("...y el informe dice «Para mirar esta semana»",
         "## Para mirar esta semana" in rep.render(HOY))

lunes2 = HOY + timedelta(days=7)
rep = informe([CAIDO, MEZCLA])
estado2, estrenan = audit.fechar(rep, estado, lunes2)
cea, amorina = rep.hallazgos
chequear("una semana después, lo que seguía abierto no es nuevo y conserva su fecha",
         not cea.nuevo and cea.desde == HOY.isoformat(), f"{cea.nuevo} {cea.desde}")
chequear("...y lo que apareció sí", amorina.nuevo and [h.cine for h in estrenan] == ["Amorina"])
texto = rep.render(lunes2)
chequear("el informe separa lo nuevo de lo que sigue abierto, con su fecha",
         "## Nuevo esta semana" in texto and "## Sigue abierto" in texto
         and "desde el 16/11" in texto, texto[:600])
chequear("el veredicto cuenta lo nuevo", "2 cosas para mirar, 1 nueva" in rep.veredicto, rep.veredicto)

lunes3 = HOY + timedelta(days=14)
rep = informe([MEZCLA])
estado3, estrenan = audit.fechar(rep, estado2, lunes3)
chequear("lo que dejó de salir se cuenta como resuelto",
         any("CEA" in r and "16/11" in r for r in rep.resueltos) and not estrenan, str(rep.resueltos))
chequear("...y queda en el informe", "Se resolvió: CEA" in rep.render(lunes3))

rep = informe([MEZCLA, CAIDO])
estado4, estrenan = audit.fechar(rep, estado3, lunes3 + timedelta(days=2))
chequear("si vuelve a los dos días es el mismo, no una novedad",
         not estrenan and rep.hallazgos[1].desde == HOY.isoformat(), f"{estrenan}")
rep = informe([MEZCLA, CAIDO])
_, estrenan = audit.fechar(rep, estado3, lunes3 + timedelta(days=20))
chequear("...y si vuelve a las tres semanas, sí", [h.cine for h in estrenan] == ["CEA"])

rep = informe([("A", "FIDBA", "sin-funciones", "empieza en 20 días y no tiene funciones")])
previo, _ = audit.fechar(rep, {"abiertos": {}, "cerrados": {}}, HOY)
rep = informe([("E", "FIDBA", "sin-funciones", "empieza en 6 días y no tiene funciones")])
_, estrenan = audit.fechar(rep, previo, HOY + timedelta(days=14))
chequear("un aviso que pasa a ser para mirar cuenta como nuevo para el centinela",
         len(estrenan) == 1 and not rep.hallazgos[0].nuevo)

rep = informe([CAIDO])
asunto, md = rep.alerta(rep.errores, HOY)
chequear("el aviso del centinela nombra la sala en el asunto",
         asunto == "🔴 Nuevo en la cartelera: CEA" and "lleva 30 días" in md, asunto)

# ── Las excepciones ───────────────────────────────────────────────────────
exc = audit.Excepciones([
    {"regla": "caido", "cine": "CEA", "motivo": "cerrado por refacciones", "hasta": "2027-03-01"},
    {"regla": "caido", "cine": "FADU", "motivo": "vencida", "hasta": "2026-10-01"},
    {"regla": "titulo-no-es-pelicula", "contiene": "torneo", "motivo": "lo quieren en la grilla"},
    {"regla": "sin-motivo", "cine": "X"},
], HOY)
rep = audit.Report(exc)
rep.accionar("CEA", "lleva 30 días sin ninguna función", regla="caido")
rep.accionar("FADU", "lleva 40 días sin ninguna función", regla="caido")
rep.accionar("MALBA", "lleva 3 días sin ninguna función", regla="caido")
chequear("una excepción vigente saca el hallazgo, la vencida no, y a otra sala no le aplica",
         [c for c, _ in rep.accion] == ["FADU", "MALBA"], str(rep.accion))
chequear("la que no tiene motivo no vale", len(exc.invalidas) == 1 and len(exc.vencidas) == 1)
chequear("«contiene» matchea sin tildes ni caja", exc.cubre("titulo-no-es-pelicula", "Amorina", "Torneo de Ajedrez"))
chequear("el informe cuenta las excepciones y las vencidas",
         "2 excepciones vigentes" in rep.render(HOY) and "1 excepción vencida" in rep.render(HOY))

# ── Un agente que se cae ──────────────────────────────────────────────────
rep = audit.Report()
audit._con(rep, "festivales", "", lambda: 1 / 0)
chequear("si un agente no puede terminar, queda dicho y cuenta como hallazgo",
         "festivales" in rep.caidos and rep.n_errors == 1
         and "no pudo terminar" in rep.render(HOY) and "💥" in rep.render(HOY))

# ── Frescura: las stories ─────────────────────────────────────────────────
root_real = audit.ROOT
with tempfile.TemporaryDirectory() as tmp:
    audit.ROOT = Path(tmp)
    for i in range(1, 8):
        d = Path(tmp) / "posts" / dia(i)
        d.mkdir(parents=True)
        if i not in (2, 3):
            (d / ".posteado-stories-only").write_text("x")
    rep = audit.Report()
    audit.check_stories(rep, HOY)
    msg = " ".join(m for _, m in rep.accion)
    chequear("dos días sin la marca de posteo son para mirar",
             "2 días" in msg and "13/11" in msg and "14/11" in msg, msg or "sin aviso")
audit.ROOT = root_real

rep = audit.Report()
audit.check_corridas(rep, [
    {"name": "Post to Instagram", "status": "completed", "conclusion": "failure", "created_at": "2026-11-15T09:00:00Z"},
    {"name": "Post to Instagram", "status": "completed", "conclusion": "success", "created_at": "2026-11-14T09:00:00Z"},
    {"name": "Scrape cartelera", "status": "completed", "conclusion": "success", "created_at": "2026-11-15T11:00:00Z"},
    {"name": "Scrape cartelera", "status": "completed", "conclusion": "failure", "created_at": "2026-11-13T11:00:00Z"},
])
chequear("un workflow clave cuya última corrida falló es para mirar; uno que se recuperó, un aviso",
         [c for c, _ in rep.accion] == ["Post to Instagram"] and "Scrape cartelera" in " ".join(rep.cronico),
         f"{rep.accion} | {rep.cronico}")

# ── El padrón ─────────────────────────────────────────────────────────────
salas, prefijos, direcciones = audit.leer_padron()
chequear("el padrón sale de index.html, con cada sala en su ciudad",
         salas.get("MALBA") == "ba" and salas.get("Cine Doré") == "madrid"
         and "Cinemark" not in salas and "all" not in salas and "MALBA" in direcciones, str(len(salas)))
chequear("la lista de cadenas es la misma en la web y en el código",
         set(prefijos) == set(audit.COMMERCIAL_PREFIXES), f"{prefijos} vs {audit.COMMERCIAL_PREFIXES}")
rep = audit.Report()
audit.check_padron(rep, salas, prefijos + ["Cine Nuevo"], direcciones, {})
chequear("si una cadena está en un lado y no en el otro, avisa",
         "Cine Nuevo" in " ".join(m for _, m in rep.accion), str(rep.accion))

# ── El monitor de festivales ──────────────────────────────────────────────
FIDBA = {"slug": "fidba", "nombre": "FIDBA", "ciclo": "Festival FIDBA", "bajada": "15.ª edición",
         "alias": ["FIDBA"], "desde": "2026-11-17", "hasta": "2026-11-22",
         "web": "https://fidba.org/x/", "logo": "data/logos/fidba.png"}
cartelera = [funcion("Sala Lúcida", "2026-11-18", "19:00", "Elton", ciclo="Festival FIDBA - Órbita"),
             funcion("Avalon", "2026-11-19", "17:00", "Hijos del Ring", ciclo="Festival FIDBA - Órbita")]
fichas, notas = monitor.revisar_registro([FIDBA], cartelera, HOY)
f = fichas[0]
chequear("un festival por empezar, con sus funciones contadas como las cuenta la web",
         f["estado"] == "proximo" and f["n"] == 2 and f["salas"] == ["Avalon", "Sala Lúcida"] and not notas,
         f"{f['estado']} {f['n']} {notas}")
chequear("...y dice cuándo", monitor.cuando_texto(f["estado"], f["desde"], f["hasta"], HOY) == "empieza mañana"
         and monitor.rango_texto(f["desde"], f["hasta"]) == "17 al 22 nov")

_, notas = monitor.revisar_registro([FIDBA], [], HOY)
chequear("empieza mañana y no tiene funciones: para mirar ya",
         [(n.sev, n.regla) for n in notas] == [("ERROR", "sin-funciones")], str(notas))
_, notas = monitor.revisar_registro([dict(FIDBA, desde="2026-12-05", hasta="2026-12-10")], [], HOY)
chequear("...a tres semanas es un aviso", [(n.sev, n.regla) for n in notas] == [("AVISO", "sin-funciones")])
_, notas = monitor.revisar_registro([dict(FIDBA, desde="2027-03-05", hasta="2027-03-10")], [], HOY)
chequear("...y a cuatro meses, nada", not notas, str(notas))

fuera = cartelera + [funcion("Arthaus", "2026-11-25", "20:00", "Otra", ciclo="Festival FIDBA - Órbita")]
_, notas = monitor.revisar_registro([FIDBA], fuera, HOY)
chequear("una función del festival fuera de sus fechas",
         [n.regla for n in notas] == ["fuera-de-fechas"] and "Arthaus" in notas[0].msg, str(notas))

otro = cartelera + [funcion("Sala Lúcida", "2026-11-20", "21:00", "Leña",
                            ciclo="Festival Internacional de Cine Documental FIDBA2026")]
_, notas = monitor.revisar_registro([dict(FIDBA, alias=["FIDBA", "FIDBA2026"])], otro, HOY)
chequear("una función que lo nombra sin su nombre del registro no aparece en su búsqueda",
         [(n.sev, n.regla) for n in notas] == [("ERROR", "otro-nombre")], str(notas))

sesiones = cartelera + [funcion("Arthaus", "2026-11-20", "20:00", "Competencia de cortos",
                                ciclo="Festival FIDBA - Cortos", director="", letterboxd="")]
_, notas = monitor.revisar_registro([FIDBA], sesiones, HOY)
chequear("un programa sin lista de películas se nombra",
         [n.regla for n in notas] == ["sin-lista"] and "Competencia de cortos" in notas[0].msg, str(notas))

_, notas = monitor.revisar_registro([{k: v for k, v in FIDBA.items() if k != "logo"}], cartelera, HOY)
chequear("al registro de un festival vigente le falta el logo",
         [n.regla for n in notas] == ["registro-incompleto"] and "logo" in notas[0].msg, str(notas))

_, notas = monitor.revisar_registro([FIDBA], cartelera, HOY, manual={"festivales": [
    {"ciclo": "FICUBA", "desde": "2026-11-10", "hasta": "2026-11-30", "cines": ["Cine Cosmos"]},
    {"ciclo": "Festival FIDBA", "desde": "2026-11-17", "hasta": "2026-11-22", "cines": []},
    {"ciclo": "DocBuenosAires", "desde": "2026-08-18", "hasta": "2026-08-23", "cines": []}]})
chequear("un festival con grilla a mano y sin registro no aparece en la pestaña",
         [(n.nombre, n.regla) for n in notas] == [("FICUBA", "sin-registro")], str(notas))

chequear("un ciclo que dice «festival» y no está en el registro es un festival suelto",
         monitor.sueltos([FIDBA], cartelera + [funcion("MALBA", "2026-11-20", ciclo="Festival de Cine Coreano")])
         == [("Festival de Cine Coreano", 1, ["MALBA"])])

# El radar
BARS = {"nombre": "Buenos Aires Rojo Sangre", "alias": ["BARS", "Rojo Sangre"], "meses": [11, 12],
        "lugar": "Buenos Aires", "web": "https://rojosangre.example/"}
notas = monitor.revisar_radar([BARS], fichas, HOY)
chequear("un festival del radar en su mes habitual y sin edición en el registro",
         [(n.sev, n.regla) for n in notas] == [("AVISO", "radar-sin-fecha")] and "noviembre" in notas[0].msg,
         str(notas))
notas = monitor.revisar_radar([dict(BARS, meses=[4])], fichas, HOY)
chequear("...fuera de su mes, nada", not notas)
notas = monitor.revisar_radar([dict(BARS, proxima={"desde": "2026-11-20", "hasta": "2026-11-30"})], fichas, HOY)
chequear("...con fecha confirmada a cuatro días, para mirar ya",
         [(n.sev, n.regla) for n in notas] == [("ERROR", "radar-inminente")], str(notas))
notas = monitor.revisar_radar([dict(BARS, proxima={"desde": "2026-11-12", "hasta": "2026-11-20"})], fichas, HOY)
chequear("...y si ya empezó, también", [n.regla for n in notas] == ["radar-en-curso"])
notas = monitor.revisar_radar([dict(BARS, ignorar_hasta="2027-01-01")], fichas, HOY)
chequear("...salvo que se haya decidido no cargarlo este año", not notas)
notas = monitor.revisar_radar([dict(BARS, ultima={"desde": "2026-11-06", "hasta": "2026-11-08"})], fichas, HOY)
chequear("...o que la edición de este año ya haya pasado", not notas, str(notas))
viejo = dict(BARS, proxima={"desde": "2025-11-20", "hasta": "2025-11-30"})
notas = monitor.revisar_radar([viejo], fichas, HOY)
chequear("un `proxima` del año pasado no tapa el aviso de este año",
         [n.regla for n in notas] == ["radar-sin-fecha"], str(notas))
notas = monitor.revisar_radar([{"nombre": "Festival Internacional de Cine Documental de Buenos Aires",
                                "alias": ["FIDBA"], "meses": [11]}], fichas, HOY)
chequear("uno del radar que ya está en el registro con su edición no se repite", not notas, str(notas))

# La web de un festival
VIEJA = ["Programación", "21/11 17:00hs Avalon", "Hijos del Ring"]
NUEVA = ["Programación", "21/11 19:30hs Avalon", "Hijos del Ring", "Función sorpresa"]
notas, estado_web = monitor.revisar_webs(fichas, {}, HOY, leer=lambda url: (VIEJA, "ok"))
chequear("la primera vez que se ve la web de un festival sólo se guarda la huella",
         not notas and estado_web["fidba"]["visto"] == HOY.isoformat())
notas, igual = monitor.revisar_webs(fichas, estado_web, HOY + timedelta(days=1), leer=lambda url: (VIEJA, "ok"))
chequear("si no cambió, ni avisa ni toca el archivo", not notas and igual == estado_web)
manana = HOY + timedelta(days=1)
notas, sin_avanzar = monitor.revisar_webs(fichas, estado_web, manana, leer=lambda url: (NUEVA, "ok"), avanzar=False)
n = notas[0] if notas else None
chequear("si cambia un horario a un día del festival, es para mirar, con la línea nueva",
         n and n.sev == "ERROR" and n.regla == "web-cambio" and "19:30hs" in n.msg and n.efimera, str(notas))
chequear("el centinela no mueve la referencia", sin_avanzar == estado_web)
notas, avanzado = monitor.revisar_webs(fichas, estado_web, manana, leer=lambda url: (NUEVA, "ok"))
chequear("el informe del lunes sí, y la semana siguiente ya no avisa",
         avanzado["fidba"]["visto"] == manana.isoformat()
         and not monitor.revisar_webs(fichas, avanzado, manana, leer=lambda url: (NUEVA, "ok"))[0])
notas, conserva = monitor.revisar_webs(fichas, estado_web, manana, leer=lambda url: (None, "HTTP 403"))
chequear("si la web no abre, se dice y se conserva la huella",
         [n.regla for n in notas] == ["web-no-abre"] and conserva == estado_web, str(notas))
chequear("el texto de una página sale sin scripts ni repeticiones",
         monitor.texto_de("<html><head><title>x</title></head><body><script>var a=1;</script>"
                          "<p>Viernes 20 &ndash; 19:00</p><p>Viernes 20 &ndash; 19:00</p>"
                          "<div>Sala L&uacute;cida</div></body></html>")
         == ["Viernes 20 – 19:00", "Sala Lúcida"])

# La sección del informe
rep = audit.Report()
audit.check_festivales(rep, sesiones, HOY, [FIDBA], [BARS])
texto = " ".join(rep.festivales)
chequear("la sección Festivales dice estado, funciones, salas y lo que hay en el radar",
         "**FIDBA** (17 al 22 nov, empieza mañana): 3 funciones por delante en 3 salas" in texto
         and "Buenos Aires Rojo Sangre" in texto, texto)

print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
raise SystemExit(1 if fallos else 0)
