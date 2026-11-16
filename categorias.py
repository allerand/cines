#!/usr/bin/env python3
"""
El reglamento de la cartelera: qué va en cada casillero de una función.

    título    una película, o un programa con nombre propio
    ciclo     un ciclo, un festival o su sección
    director  una o más personas
    sala      una sala que la web conoce, en su ciudad

Una "mezcla" es un dato en el casillero de otro. El 15/11/2026 la Sala
Lugones publicó "Homenaje a John Huston" como si fuera una película, al lado
de las películas del homenaje: el scraper no había podido leer el programa y
puso el nombre del ciclo donde va el título. Ese mismo día la cartelera tenía
otras mezclas que nadie había visto: «Ciclo Cuadro a Cuadro: Ánima Buenos
Aires» como título en el Borges, "Documental" como ciclo en Filo, un torneo de
ajedrez entre las películas de Amorina, «Festival Rizoma-calada» en Sala Equis.

Acá están las reglas, en un solo lugar, para los dos que las usan:

  - run.py, en cada scrape: `portero` frena lo que es seguro que no es una
    película (un título que es el nombre de un ciclo de esa sala o de un
    festival del registro) antes de que llegue a la web y a las stories.
    Mejor una fila menos que un ciclo en el lugar de una película.
  - scripts/audit.py, cada lunes y en el centinela diario: `revisar` marca
    todo lo demás, que necesita ojos (o un agente) para decidir.

Sólo stdlib, sin red: se puede importar desde cualquier lado.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Iterable, NamedTuple, Optional

ERROR, AVISO = "ERROR", "AVISO"

# Las cadenas, por prefijo del nombre de la sala. Es la misma lista que tienen
# index.html y run.py; scripts/audit.py la toma de acá.
COMMERCIAL_PREFIXES = ("Cinemark", "Hoyts", "Cinépolis", "Cinepolis", "Showcase",
                       "Multiplex", "Cines Pixel")


def norm(t: str) -> str:
    """Para comparar: sin tildes, caja ni puntuación (igual que
    scraper.titulo_norm, que no se puede importar sin sus dependencias)."""
    t = re.sub(r"['’‘`´]", "", t or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", t.lower()))


def ciclo_base(ciclo: str) -> str:
    """El ciclo sin la sección: "Festival FIDBA - Órbita" → "Festival FIDBA".
    Es el mismo corte que hace unificar_ciclos_festivales."""
    return re.split(r"\s+[-–—]\s+", (ciclo or "").strip(), maxsplit=1)[0].strip()


# ---------------------------------------------------------------------------
# Vocabulario
# ---------------------------------------------------------------------------

# Con qué empieza el nombre de un ciclo. Sirve para dos reglas: un título que
# arranca así y sigue con ":" trae el ciclo pegado («Ciclo de Cine Peruano:
# Manco Cápac»); uno que arranca así y no tiene ni director ni Letterboxd
# probablemente ES un ciclo («Semana de los Festivales de Cine de Málaga…»).
_MARCA = (r"ciclo|festival|muestra|retrospectiva|homenaje\s+a|foco|semana\s+de|"
          r"panorama|competencia|jornadas?|bienal|marat[óo]n")
# "16º Festival…", "XXVII Ciclo…"
_ORDINAL = r"(?:\d{1,3}\s*[°ºª.]{0,2}\s*|[IVXLC]{1,7}\s+)?"
# La F doble es de Sala Equis, que escribe "Ffestival Rizoma-simulacro".
_EMPIEZA_CICLO = re.compile(rf"^\s*{_ORDINAL}f?(?:{_MARCA})\b", re.IGNORECASE)
_CICLO_Y_PELICULA = re.compile(
    rf"^\s*{_ORDINAL}f?(?:{_MARCA})\b[^:|]{{0,70}}?[:|]\s+\S", re.IGNORECASE)

# Separadores entre un prefijo y el resto del título. El guion sin espacios es
# de Sala Equis ("Festival Rizoma-calada"); el mínimo de largo del prefijo
# deja afuera a "Spider-Man" y "X-Men".
_SEPARADOR = re.compile(r":\s+|\.\s+|\s+[-–—|]\s+|(?<=\w)-(?=\w)")
PREFIJO_MIN = 10          # letras del prefijo, ya normalizado
PREFIJO_VECES = 3         # títulos distintos de la sala que lo comparten

_NOMBRE = r"[A-ZÁÉÍÓÚÑÜ][\wáéíóúñüöäëïèàçã'’.-]*"
# ", de Boom Boom Kid" o ") de Marta György-Kessler": la coma o el paréntesis
# antes del "de" no dejan dudas.
_DIRECTOR_PEGADO = re.compile(rf"[,)]\s*de[\s ]+{_NOMBRE}")
_SOLO_NOMBRES = re.compile(
    rf"^{_NOMBRE}(?:\s+(?:(?:de|del|la|las|los|van|von|y|e)\s+)*{_NOMBRE}){{1,3}}$")

# Versión, formato o tipo de sesión: son datos de la función, no del título.
_ETIQUETA = re.compile(
    r"\bv\.?\s?o\.?\s?s\.?\s?e\.?(?=\W|$)|\(\s*v\.?o\.?\s*\)|\bsubtitulad[ao]s?\b|"
    r"\bdoblad[ao]s?\b|\bsesi[óo]n\s+teta\b|\b(?:35|16|70)\s?mm\b|"
    r"\bcopia\s+(?:nueva|restaurada)\b|\bversi[óo]n\s+restaurada\b|"
    r"\bpreestreno\b|\bavant[- ]premi[eè]re\b", re.IGNORECASE)

# Actividades que una sala anuncia en la misma agenda que el cine.
_ACTIVIDAD = re.compile(
    r"^\s*(?:torneo|taller|charla|conversatorio|master\s?class|"
    r"clase\s+(?:abierta|magistral)|seminario|curso|concierto|recital|"
    r"presentaci[óo]n\s+del?\s+libro|mesa\s+redonda|visita\s+guiada|"
    r"inauguraci[óo]n|entrega\s+de\s+premios|ceremonia|convocatoria|feria|"
    r"fiesta|workshop|laboratorio|karaoke|bingo|trivia|stand\s?up|dj\s+set)\b",
    re.IGNORECASE)
_EN_VIVO = re.compile(
    r"\bballet\b|\blive\s+roh\b|\bmet\s+opera\b|\bnational\s+theatre\s+live\b|"
    r"\b[óo]pera\b.{0,40}\b(?:en\s+vivo|en\s+directo|live)\b", re.IGNORECASE)

# La ficha pegada al título: "(1995, 55 min.)", "90 min", "(2024)".
_FICHA_EN_TITULO = re.compile(
    r"\b\d{2,3}\s?(?:min\.?|minutos)(?=\W|$)|\(\s*(?:[^()]{0,40},\s*)?(?:19|20)\d{2}\s*\)",
    re.IGNORECASE)
_HORARIO_EN_TITULO = re.compile(
    r"\b\d{1,2}[:.]\d{2}\s?hs?\b|\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|"
    r"s[áa]bado|domingo)\s+\d{1,2}\b", re.IGNORECASE)

# Lo que NO es un ciclo aunque venga en esa columna.
GENEROS = {norm(g) for g in (
    "documental", "documentales", "ficción", "ficciones", "animación", "comedia",
    "drama", "terror", "thriller", "suspenso", "acción", "aventura", "aventuras",
    "romance", "musical", "western", "ciencia ficción", "fantasía", "policial",
    "biopic", "cortometraje", "cortometrajes", "largometraje", "largometrajes")}
TIPOS = {norm(t) for t in (
    "cine", "película", "películas", "proyección", "proyecciones", "función",
    "funciones", "evento", "eventos", "actividad", "actividades", "agenda",
    "programación", "cartelera", "audiovisual", "audiovisuales", "general",
    "otros", "varios", "sin categoría")}
# Etiquetas de programación: no son un ciclo, pero las salas las usan en esa
# columna a propósito (el MALBA con "Estreno" y "Continúa", la Lugones con
# "Estreno") y se quedan.
ETIQUETAS = {norm(e) for e in (
    "estreno", "estrenos", "continúa", "continúan", "reestreno", "reestrenos",
    "preestreno", "función especial", "funciones especiales", "trasnoche",
    "matiné", "doble función", "últimas funciones", "última función")}

# Palabras comunes que ningún ciclo lleva en mayúsculas (Mateo, 8/11/2026:
# "no me pongas los ciclos en mayúsculas nunca"). Una sigla sí puede: FIDBA.
_PALABRAS_GRITADAS = {norm(p) for p in (
    "cine", "ciclo", "festival", "muestra", "estreno", "especial", "programa",
    "foco", "homenaje", "retrospectiva", "película", "películas", "función",
    "clásicos", "argentino", "cortos", "nuevo", "nueva")}
_ROMANO = re.compile(r"^X{0,3}(?:IX|IV|V?I{0,3})$")

RELLENOS = {norm(r) for r in (
    "desconocido", "desconocida", "varios", "varias", "varios directores",
    "varias directoras", "varias autoras", "varios autores", "anónimo", "n/a",
    "sin datos", "a confirmar", "vv.aa.", "s/d")}


# ---------------------------------------------------------------------------
# Reglas: qué pasa y qué hacer (los textos del informe)
# ---------------------------------------------------------------------------

REGLAS = {
    # --- el título ---
    "titulo-es-ciclo": (
        ERROR, "hay funciones que dicen el nombre de un ciclo en vez de la película",
        "el scraper no pudo leer el programa del ciclo"),
    "titulo-es-festival": (
        ERROR, "hay funciones que se llaman como un festival del registro",
        "es el evento del festival, no una película: va película por película "
        "o se descarta en manual_screenings.json"),
    "titulo-con-ciclo": (
        ERROR, "el título trae el ciclo pegado adelante",
        "el scraper tiene que partirlo: el ciclo a su columna y el título solo"),
    "titulo-con-festival": (
        ERROR, "el título nombra un festival del registro y el ciclo no",
        "así la función no aparece en la búsqueda del festival: el nombre va al ciclo"),
    "titulo-parece-ciclo": (
        ERROR, "hay títulos que parecen el nombre de un ciclo o de un festival, "
               "sin director ni ficha",
        "confirmar contra la fuente si es una película; si es un ciclo, cargar "
        "sus películas una por una"),
    "titulo-con-director": (
        ERROR, "el título trae al director pegado",
        "el scraper tiene que partirlo: sin eso no encuentra la ficha"),
    "titulo-quizas-con-director": (
        AVISO, "títulos que quizás traen al director pegado (terminan en «de Nombre Apellido»)",
        "mirar la fuente"),
    "titulo-no-es-pelicula": (
        ERROR, "hay actividades que no son películas",
        "se descartan en el scraper o en manual_screenings.json"),
    "titulo-con-etiqueta": (
        AVISO, "títulos con la versión o el tipo de sesión pegados (VOSE, 35 mm)",
        "limpiar en el scraper"),
    "titulo-con-ficha": (
        AVISO, "títulos con el año o la duración pegados", "limpiar en el scraper"),
    "titulo-con-horario": (
        AVISO, "títulos con un día o una hora adentro", "limpiar en el scraper"),
    "titulo-gritado": (
        AVISO, "títulos con un tramo en mayúsculas", "pasarlos por run._fix_caps"),
    # --- el ciclo ---
    "ciclo-es-genero": (
        ERROR, "la columna Ciclo trae el género de la película",
        "el género no es un ciclo: va vacío o con el ciclo de verdad"),
    "ciclo-es-tipo": (
        ERROR, "la columna Ciclo trae el tipo de actividad («Cine»)",
        "no es un ciclo: va vacío"),
    "ciclo-igual-al-titulo": (
        AVISO, "funciones cuyo ciclo es el mismo título", "el ciclo va vacío"),
    "ciclo-escrito-distinto": (
        AVISO, "un mismo ciclo escrito de dos maneras",
        "la búsqueda por ciclo los separa: unificar la escritura"),
    "ciclo-mal-escrito": (
        AVISO, "ciclos con la puntuación rota", "arreglar la escritura en el scraper"),
    "ciclo-gritado": (
        ERROR, "hay ciclos con palabras en mayúsculas",
        "ningún ciclo va gritado: pasarlo por run._fix_caps"),
    # --- el director ---
    "director-es-otra-cosa": (
        ERROR, "en el director está el título o un festival",
        "el scraper leyó otro campo"),
    "director-relleno": (
        AVISO, "directores de relleno («Desconocido», «Varios»)", "mejor vacío"),
    "director-con-de": (
        AVISO, "directores que empiezan con «de»", "limpiar en el scraper"),
    "director-con-numeros": (
        AVISO, "directores con años o duraciones adentro", "el scraper leyó la ficha entera"),
    # --- la sala ---
    "sala-desconocida": (
        ERROR, "hay funciones en una sala que la web no conoce",
        "sumarla a index.html (chip y dirección) o corregir el nombre"),
    "sala-de-otra-ciudad": (
        ERROR, "hay funciones de una sala de la otra ciudad",
        "Madrid va en cartelera-madrid.json y Buenos Aires en cartelera.json"),
    "festival-de-afuera-adentro": (
        ERROR, "hay funciones de un festival de afuera en la cartelera de Buenos Aires",
        "van sólo en su archivo propio"),
}


class Mezcla(NamedTuple):
    regla: str
    cine: str
    detalle: str      # ejemplo que se lee solo: "21/11 19:00: 'Homenaje a John Huston'"
    valor: str        # el dato que está mal (para matchear una excepción)
    fila: dict        # la primera función donde aparece
    n: int = 1        # en cuántas funciones aparece


def _es_comercial(cine: str) -> bool:
    return cine.startswith(COMMERCIAL_PREFIXES)


def _q(valor: str) -> str:
    """Un dato entre comillas para el informe, sin los espacios duros que
    traen algunas fuentes (el MALBA escribe "de\\xa0Boom Boom Kid")."""
    return "«" + " ".join(str(valor).replace(" ", " ").split()) + "»"


def _donde(s: dict) -> str:
    f = s.get("fecha", "")
    dia = f"{f[8:10]}/{f[5:7]}" if len(f) == 10 else f
    return f"{dia} {s.get('hora', '')}".strip()


def ciclos_por_sala(filas: Iterable[dict]) -> dict:
    """{sala: {ciclo normalizado: (como se escribe, {títulos normalizados})}}"""
    out: dict = defaultdict(dict)
    for s in filas:
        base = ciclo_base(s.get("ciclo") or "")
        if not base:
            continue
        k = norm(base)
        if not k:
            continue
        escrito, titulos = out[s.get("cine", "")].setdefault(k, (base, set()))
        titulos.add(norm(s.get("title_es") or s.get("title") or ""))
    return out


def nombres_de_festivales(festivales: Optional[list]) -> dict:
    """{nombre normalizado: festival} con el nombre, el ciclo y los alias de
    cada festival del registro (data/festivales.json)."""
    out: dict = {}
    for f in festivales or []:
        for n in [f.get("nombre"), f.get("ciclo")] + list(f.get("alias") or []):
            k = norm(n or "")
            if k:
                out.setdefault(k, f)
    return out


def _tramo_gritado(texto: str) -> str:
    """Dos o más palabras seguidas en mayúsculas dentro de un texto que no está
    todo gritado: "Ingmar Bergman: seis ensayos. CUANDO HUYE EL DÍA"."""
    letras = [c for c in texto if c.isalpha()]
    if not letras or all(c.isupper() for c in letras):
        return ""       # todo en mayúsculas es otra regla (y otra causa)
    racha: list[str] = []
    mejor: list[str] = []
    for w in texto.split():
        solo = re.sub(r"[^\wÁÉÍÓÚÑÜáéíóúñü]", "", w)
        alfa = [c for c in solo if c.isalpha()]
        if len(alfa) >= 2 and all(c.isupper() for c in alfa) and not _ROMANO.match(solo):
            racha.append(w)
            if len(racha) > len(mejor):
                mejor = list(racha)
        else:
            racha = []
    return " ".join(mejor) if len(mejor) >= 2 and sum(len(w) for w in mejor) >= 7 else ""


def _palabra_gritada(ciclo: str) -> str:
    """Una palabra común en mayúsculas dentro de un ciclo: "CINE en 16mm"."""
    for w in ciclo.split():
        solo = re.sub(r"[^\wÁÉÍÓÚÑÜáéíóúñü]", "", w)
        if len(solo) >= 4 and solo.isupper() and norm(solo) in _PALABRAS_GRITADAS:
            return w
    return ""


def director_en_titulo(titulo: str) -> tuple[str, str, bool]:
    """(título sin el director, director, seguro). ("", "", False) si no hay.

    Seguro: «…?, de Boom Boom Kid» y «…(Meeting the Buddha) de Marta
    György-Kessler». Dudoso: «El príncipe de Nanawa de Clarisa Navas», que
    tiene la misma forma que «El secreto de Vera Drake».
    """
    t = (titulo or "").replace(" ", " ").strip()
    m = _DIRECTOR_PEGADO.search(t)
    if m:
        corte = m.start() + (1 if t[m.start()] == ")" else 0)
        resto = re.sub(r"^[,)]?\s*de\s+", "", t[m.start():]).strip()
        return t[:corte].strip(" ,"), resto, True
    # De derecha a izquierda: en «El príncipe de Nanawa de Clarisa Navas» el
    # director es lo que sigue al último "de".
    for m in reversed(list(re.finditer(r"\s+de\s+", t))):
        cola = t[m.end():].strip()
        if (_SOLO_NOMBRES.match(cola) and len(t[:m.start()].split()) >= 2
                and not any(w.isupper() and len(w) > 1 for w in cola.split())):
            return t[:m.start()].strip(), cola, False
    return "", "", False


def _prefijo(titulo: str) -> tuple[str, str]:
    """(prefijo, resto) por el primer separador del título, o ("", "")."""
    m = _SEPARADOR.search(titulo or "")
    if not m or not titulo[m.end():].strip():
        return "", ""
    return titulo[:m.start()].strip(), titulo[m.end():].strip()


def prefijos_repetidos(filas: Iterable[dict]) -> dict:
    """{(sala, prefijo normalizado): prefijo} para los prefijos que comparten
    varios títulos distintos de una sala: es un ciclo pegado al título.

    El Borges publica «Ingmar Bergman: seis ensayos. PERSONA», «…SONATA DE
    OTOÑO», «…UN VERANO CON MÓNICA»: ninguna palabra dice "ciclo", pero cinco
    películas distintas no empiezan igual por casualidad. Las cadenas quedan
    afuera: ahí sí hay sagas enteras en cartel («El Señor de los Anillos: …»).
    """
    vistos: dict = defaultdict(set)
    escrito: dict = {}
    for s in filas:
        cine = s.get("cine", "")
        if _es_comercial(cine):
            continue
        pre, _ = _prefijo(s.get("title_es") or "")
        k = norm(pre)
        if len(k.replace(" ", "")) < PREFIJO_MIN:
            continue
        vistos[(cine, k)].add(norm(s.get("title_es") or ""))
        escrito.setdefault((cine, k), pre)
    return {k: escrito[k] for k, ts in vistos.items() if len(ts) >= PREFIJO_VECES}


# ---------------------------------------------------------------------------
# El portero: lo que es seguro que no es una película
# ---------------------------------------------------------------------------

def _motivo_seguro(s: dict, ciclos: dict, festivales: dict) -> tuple[str, str]:
    """(regla, motivo) si la fila es, sin dudas, un ciclo o un festival puesto
    en el lugar de una película; ("", "") si no."""
    cine = s.get("cine", "")
    titulo = s.get("title_es") or s.get("title") or ""
    t = norm(titulo)
    if not t:
        return "", ""
    propio = norm(ciclo_base(s.get("ciclo") or ""))
    # Un ciclo de esa sala con OTRAS películas. Si la fila es del propio ciclo
    # (una maratón que se llama como la trilogía) no es este caso, y un ciclo
    # de una sola película que se llama como ella tampoco.
    conocido = ciclos.get(cine, {}).get(t)
    if conocido and t != propio and (conocido[1] - {t}):
        return ("titulo-es-ciclo",
                f"«{titulo}» es un ciclo de {cine}, no una película")
    fest = festivales.get(t)
    if fest and t != propio:
        return ("titulo-es-festival",
                f"«{titulo}» es el festival {fest.get('nombre', '')}, no una película")
    return "", ""


def clave_a_mano(s: dict) -> tuple:
    """Cómo se reconoce una función cargada a mano: sala, fecha y hora. El
    título no entra: el enrichment y unificar_fichas lo pueden reescribir."""
    return (s.get("cine", ""), s.get("fecha", ""), s.get("hora", ""))


def portero(filas: list, previas: Iterable[dict] = (), festivales: Optional[list] = None,
            a_mano: Iterable[tuple] = (), sin_registro: Iterable[str] = ()) -> tuple[list, list]:
    """Separa lo que no se publica. Devuelve (quedan, retenidas).

    `filas`: la lista final de run.py (dicts de cartelera.json).
    `previas`: las funciones de la corrida anterior. De ahí salen los ciclos
        que cada sala ya tenía: el día que el runner no pudo leer ninguna
        página de ciclo del CTBA, las películas del homenaje no estaban en la
        corrida, y sin memoria el nombre del ciclo pasaba por una película.
    `festivales`: el registro (data/festivales.json).
    `a_mano`: clave_a_mano de las funciones cargadas a mano, que no se tocan:
        lo que alguien escribió a propósito no lo saca una regla.
    `sin_registro`: las salas a las que no les aplica el registro de
        festivales (las de Madrid: el registro es sólo de Argentina).

    Cada retenida es la fila más `motivo` y `regla`. Van a cartelera.json
    (clave `retenidas`) para que la auditoría las cuente: no se publican, pero
    tampoco se pierden.

    Corrido sobre las 330 corridas de julio a noviembre de 2026 habría frenado
    ocho títulos, todos nombres de ciclos o de festivales: los tres de la
    Lugones del 15/11, «Ficuba» en Cacodelphia, «La mujer y el cine» en el
    MALBA, el Festival de Cine Experimental de Bogotá en el Borges y dos
    festivales en la Biblioteca del Congreso. Ninguna película.
    """
    ciclos = ciclos_por_sala(list(previas) + list(filas))
    fests = nombres_de_festivales(festivales)
    a_mano, sin_registro = set(a_mano), set(sin_registro)
    quedan, retenidas = [], []
    for s in filas:
        regla, motivo = "", ""
        if clave_a_mano(s) not in a_mano:
            regla, motivo = _motivo_seguro(
                s, ciclos, {} if s.get("cine", "") in sin_registro else fests)
        if regla:
            retenidas.append(dict(s, regla=regla, motivo=motivo))
        else:
            quedan.append(s)
    return quedan, retenidas


# ---------------------------------------------------------------------------
# La revisión completa (auditoría)
# ---------------------------------------------------------------------------


def revisar(filas: list, *, previas: Iterable[dict] = (), festivales: Optional[list] = None,
            salas: Optional[dict] = None, ciudad: str = "",
            a_mano: Iterable[tuple] = (), excepcion=None) -> list[Mezcla]:
    """Todas las mezclas de una cartelera.

    `filas`: las funciones a revisar (las que todavía no pasaron).
    `previas`: funciones de corridas anteriores, para saber qué ciclos tenía
        cada sala (ver portero).
    `salas`: {sala: ciudad} según index.html; sin eso no se revisan las salas.
    `ciudad`: "ba" o "madrid", la de `filas`.
    `a_mano`: clave_a_mano de las funciones cargadas a mano. Lo que alguien
        escribió a propósito no se discute por la forma del título: una sesión
        de festival sin lista de películas se carga como «Competencia
        Internacional» y está bien. Las reglas seguras les aplican igual.
    `excepcion(regla, cine, valor, fila) -> bool`: lo que ya se miró y se
        aceptó (data/audit_excepciones.json).
    """
    a_mano = set(a_mano)
    ciclos = ciclos_por_sala(list(previas) + list(filas))
    fests = nombres_de_festivales(festivales)
    alias_fest = sorted(((k, f) for k, f in fests.items() if not f.get("archivo")),
                        key=lambda kv: -len(kv[0]))
    de_afuera = [f for f in festivales or [] if f.get("archivo")]
    repetidos = prefijos_repetidos(filas)

    # Títulos que la cartelera ya conoce con su director: confirman un «X de
    # Nombre Apellido» dudoso.
    con_director: dict = defaultdict(set)
    for s in filas:
        if s.get("director"):
            con_director[norm(s.get("title_es") or "")].add(norm(s["director"]))

    # Cada ciclo, escrito de todas las formas en que aparece (por ciudad).
    formas: dict = defaultdict(lambda: defaultdict(set))
    for s in filas:
        base = ciclo_base(s.get("ciclo") or "")
        if base:
            formas[norm(base).replace(" ", "")][base].add(s.get("cine", ""))

    encontradas: dict = {}

    def marcar(regla: str, s: dict, valor: str, detalle: str = "") -> None:
        cine = s.get("cine", "?")
        if excepcion and excepcion(regla, cine, valor, s):
            return
        # Una mezcla por (regla, sala, dato): las cuarenta funciones de una
        # película mal escrita son un solo problema, con su cuenta.
        k = (regla, cine, valor)
        if k in encontradas:
            encontradas[k] = encontradas[k]._replace(n=encontradas[k].n + 1)
        else:
            encontradas[k] = Mezcla(regla, cine, detalle or f"{_donde(s)}: {_q(valor)}", valor, s)

    for s in filas:
        cine = s.get("cine", "?")
        titulo = (s.get("title_es") or "").strip()
        director = (s.get("director") or "").strip()
        ciclo = (s.get("ciclo") or "").strip()
        base = ciclo_base(ciclo)
        t, c, d = norm(titulo), norm(base), norm(director)
        sin_ficha = not director and not s.get("letterboxd")
        comercial = _es_comercial(cine)
        manual = clave_a_mano(s) in a_mano

        # ── La sala ──────────────────────────────────────────────────────
        if salas is not None and not comercial:
            if cine not in salas:
                marcar("sala-desconocida", s, cine, f"{_q(cine)} ({_donde(s)}: {_q(titulo)})")
            elif ciudad and salas[cine] != ciudad:
                marcar("sala-de-otra-ciudad", s, cine, f"{_q(cine)} está en la cartelera equivocada")
        if ciudad == "ba":
            for f in de_afuera:
                nombres = {norm(f.get("nombre") or "")} | {norm(a) for a in f.get("alias") or []}
                if cine in (f.get("sedes") or {}) or (c and c in nombres):
                    marcar("festival-de-afuera-adentro", s, f.get("nombre", ""),
                           f"{f.get('nombre')}: {cine}, {_donde(s)}, {_q(titulo)}")

        # ── El título ────────────────────────────────────────────────────
        regla, _ = _motivo_seguro(s, ciclos, fests)
        if regla:
            marcar(regla, s, titulo)
        elif titulo:
            pre, _resto = _prefijo(titulo)
            fest_en_titulo = next(
                (f for k, f in alias_fest
                 if f" {k} " in f" {t} " and t != k
                 and not any(f" {a} " in f" {c} " for a, g in alias_fest if g is f)), None)
            if manual:
                pass
            elif _CICLO_Y_PELICULA.match(titulo) or (cine, norm(pre)) in repetidos:
                marcar("titulo-con-ciclo", s, titulo)
            elif fest_en_titulo:
                marcar("titulo-con-festival", s, titulo)
            elif _EMPIEZA_CICLO.match(titulo) and sin_ficha and t != c:
                marcar("titulo-parece-ciclo", s, titulo)
            elif (_ACTIVIDAD.match(titulo) or _EN_VIVO.search(titulo)) and sin_ficha:
                marcar("titulo-no-es-pelicula", s, titulo)

            limpio, nombre, seguro = director_en_titulo(titulo)
            if nombre and not manual:
                confirmado = norm(nombre) in con_director.get(norm(limpio), set())
                if seguro or confirmado:
                    marcar("titulo-con-director", s, titulo)
                elif not director and (s.get("year") or s.get("duration")):
                    # Dudoso, salvo por el contexto: la fuente dio año o
                    # duración y el director no aparece en ningún lado. Sin
                    # eso, «ALIENTO - 10 años del Programa de Cine UTDT»
                    # también termina en "de Algo Algo".
                    marcar("titulo-quizas-con-director", s, titulo)

            if not comercial:
                if _ETIQUETA.search(titulo):
                    marcar("titulo-con-etiqueta", s, titulo)
                if _FICHA_EN_TITULO.search(titulo):
                    marcar("titulo-con-ficha", s, titulo)
                if _HORARIO_EN_TITULO.search(titulo):
                    marcar("titulo-con-horario", s, titulo)
                if _tramo_gritado(titulo):
                    marcar("titulo-gritado", s, titulo)

        # ── El ciclo ─────────────────────────────────────────────────────
        if base:
            if c in GENEROS:
                marcar("ciclo-es-genero", s, base, f"{_q(base)} ({_q(titulo)})")
            elif c in TIPOS:
                marcar("ciclo-es-tipo", s, base, f"{_q(base)} ({_q(titulo)})")
            elif (c == t and c not in ETIQUETAS and not manual
                  and len(ciclos.get(cine, {}).get(c, ("", {t}))[1]) == 1):
                marcar("ciclo-igual-al-titulo", s, base, f"{_donde(s)}: {_q(titulo)}")
            if _palabra_gritada(ciclo) or _tramo_gritado(ciclo):
                marcar("ciclo-gritado", s, ciclo, _q(ciclo))
            if (re.search(r"[:;,]\S", re.sub(r"\d[:.,]\d", "", ciclo)) or "  " in ciclo
                    or re.search(r"\s[.,;:](?:\s|$)", ciclo) or re.search(r"[-–—:,;/]$", ciclo)):
                marcar("ciclo-mal-escrito", s, ciclo, _q(ciclo))
            variantes = formas[c.replace(" ", "")]
            if len(variantes) > 1:
                # La forma más usada es la buena; se marca la otra.
                buena = max(variantes, key=lambda v: (len(variantes[v]), v))
                if base != buena:
                    marcar("ciclo-escrito-distinto", s, base, f"{_q(base)} y {_q(buena)}")

        # ── El director ──────────────────────────────────────────────────
        if director:
            # Que el director se llame como el ciclo no es una mezcla: las
            # retrospectivas llevan el nombre del director ("James Benning").
            if d and (d == t or d in fests):
                marcar("director-es-otra-cosa", s, director, f"{_q(titulo)}: {_q(director)}")
            elif d in RELLENOS:
                marcar("director-relleno", s, director, f"{_q(titulo)}: {_q(director)}")
            if re.match(r"de\s+[A-ZÁÉÍÓÚÑ]", director):
                marcar("director-con-de", s, director, f"{_q(titulo)}: {_q(director)}")
            if re.search(r"\b(?:19|20)\d{2}\b|\b\d{2,3}\s?(?:min|')", director):
                marcar("director-con-numeros", s, director, f"{_q(titulo)}: {_q(director)}")

    return list(encontradas.values())
