#!/usr/bin/env python3
"""
Test local de check_cobertura (scripts/audit.py), sin red ni git.

    python3 test_audit_cobertura.py

La auditoría existe para romper un silencio: cada scraper atrapa su excepción
y devuelve [], así que un cine se cae de la web sin que nada falle. Estos casos
cubren las tres formas en que la auditoría se quedaba callada o mandaba a
arreglar lo que no era:

  · Un cine caído hace más de media ventana tenía mediana 0, y con mediana 0 no
    se avisaba. El Museo del Cine llevaba ocho días en cero sin figurar en
    ningún informe: cuanto más viejo el problema, más silencioso el informe.
  · Cuando la sonda se comía un 403 —la fuente bloqueando al runner, el mismo
    bloqueo que frena al scraper— el informe decía "revisá su scraper", que
    manda a reescribir un parser intacto.
  · Una sonda que mide 0 ítems (el cine no programó) se trataba igual que una
    que no pudo medir, y salía como hallazgo.
"""
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import audit                                        # noqa: E402

HOY = date(2026, 8, 24)


def _snaps(series: dict[str, list[int]]) -> dict[str, Counter]:
    """{cine: [hoy, ayer, ...]} → snapshots por día como los arma git_snapshots."""
    n = max(len(v) for v in series.values())
    dias = [date.fromordinal(HOY.toordinal() - i).isoformat() for i in range(n)]
    return {d: Counter({cine: vals[i] for cine, vals in series.items() if vals[i]})
            for i, d in enumerate(dias)}


def _correr(series, probes=None, screenings=None):
    rep = audit.Report()
    audit.check_cobertura(rep, screenings or [], HOY, _snaps(series), probes or {})
    return ({cine: msg for cine, msg in rep.accion}, " ".join(rep.cronico))


def main() -> int:
    fallos = 0

    def chequear(desc, ok, detalle=""):
        nonlocal fallos
        print(f"{'ok ' if ok else 'MAL'} {desc}" + (f" → {detalle}" if not ok else ""))
        if not ok:
            fallos += 1

    # 1. Caído hace más días que media ventana: la mediana ya es 0 y antes se
    #    perdía. Tiene que avisar igual, y decir hace cuánto.
    acc, _ = _correr({"Museo del Cine": [0] * 8 + [5, 5, 5, 2, 2, 5]})
    msg = acc.get("Museo del Cine", "")
    chequear("cine caído hace 8 días sigue avisando", "8 días" in msg, msg or "sin aviso")
    chequear("dice cuánto traía cuando andaba", "~5 por día" in msg, msg)

    # 2. La sonda se come un 403: es la fuente bloqueando, no el parser.
    acc, _ = _correr({"CCK": [0, 0] + [15] * 10},
                     probes={"CCK": (None, f"{audit._RECHAZO}HTTP 403")})
    msg = acc.get("CCK", "")
    chequear("un 403 en la sonda no manda a revisar el parser",
             "No es el parser" in msg and "proxy" in msg, msg or "sin aviso")

    # 3. La sonda mide y la fuente no publica nada: el cine no programó.
    acc, cron = _correr({"Cine Gaumont": [0, 0, 0] + [30] * 10},
                        probes={"Cine Gaumont": (0, "ítems en la listing")})
    chequear("fuente vacía medida no es un hallazgo",
             "Cine Gaumont" not in acc and "Cine Gaumont" not in cron, str(acc))

    # 4. La sonda encuentra programación y nosotros no: ahí sí, el parser.
    acc, _ = _correr({"Centro Cultural 25 de Mayo": [0, 0] + [1] * 10},
                     probes={"Centro Cultural 25 de Mayo": (5, "ítems en la listing")})
    msg = acc.get("Centro Cultural 25 de Mayo", "")
    chequear("fuente con ítems y nosotros en cero → scraper roto",
             "El scraper se rompió" in msg, msg or "sin aviso")

    # 5. Sala chica que entra y sale del cero: se nombra, sin gritar.
    acc, cron = _correr({"CEA": [0, 3, 1, 0, 0, 4, 5, 1, 3, 2, 1, 3]})
    chequear("un hueco de un día en una sala chica no es ERROR", "CEA" not in acc, str(acc))
    chequear("...pero igual figura en el informe", "CEA" in cron, cron or "no figura")

    # 6. Una sala de volumen en cero avisa desde el primer día, sin esperar racha.
    acc, _ = _correr({"Cine Gaumont": [0] + [30] * 12})
    chequear("una sala de volumen en cero avisa enseguida", "Cine Gaumont" in acc, str(acc))

    # 7. Un cine que nunca trajo nada en la ventana no tiene con qué comparar.
    acc, cron = _correr({"Sala Fantasma": [0] * 12})
    chequear("sin histórico no se inventa un hallazgo",
             "Sala Fantasma" not in acc and "Sala Fantasma" not in cron, str(acc))

    # 8. El máximo como "lo habitual" se lo lleva un día de datos basura: Cosmos
    #    llegó a publicar 843 funciones el día que cada película se llevaba los
    #    horarios de todas las demás. La mediana de los días con funciones no.
    acc, _ = _correr({"Cine Cosmos": [0, 0, 0, 0, 10, 68, 8, 16, 16, 24, 32, 843, 12, 12]})
    msg = acc.get("Cine Cosmos", "")
    chequear("un día de datos basura no define 'lo habitual'",
             "843" not in msg and "~16 por día" in msg, msg or "sin aviso")

    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
