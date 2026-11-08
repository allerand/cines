"""Ningún ciclo en mayúsculas en la web (pedido de Mateo, 8/11/2026).

El Doré los publica gritados ("EL PRESENTE EN ESCENA. EL CINE ARGENTINO DEL
SIGLO XXI") y run.py los pasa por _fix_caps. Acá se prueba esa conversión, y
que en los JSON publicados no haya ninguno en mayúsculas.

    python3 test_ciclos_mayusculas.py
"""
import json
from pathlib import Path

from test_sala_lucida import helpers_de_run

CASOS = {
    "EL PRESENTE EN ESCENA. EL CINE ARGENTINO DEL SIGLO XXI":
        "El Presente en Escena. El Cine Argentino del Siglo XXI",
    "¡AL HOLLYWOOD PARISINO! MULTIVERSIONES EN LA II REPÚBLICA":
        "¡Al Hollywood Parisino! Multiversiones en la II República",
    "MI PRIMER FESTIVAL / FILMOTECA JR.": "Mi Primer Festival / Filmoteca Jr.",
    "LYCEUM CLUB FEMENINO / GUERRA CIVIL. 90 AÑOS": "Lyceum Club Femenino / Guerra Civil. 90 Años",
    "Ciclo LGBTIQ(X)": "Ciclo LGBTIQ(X)",
    "El presente en escena. Cine argentino del siglo XXI":
        "El presente en escena. Cine argentino del siglo XXI",
}


def gritado(s: str) -> bool:
    letras = [c for c in s if c.isalpha()]
    return len(letras) > 3 and all(c.isupper() for c in letras)


def main() -> int:
    _, fix_caps = helpers_de_run()
    fallos = 0
    for entrada, esperado in CASOS.items():
        sale = fix_caps(entrada)
        ok = sale == esperado
        fallos += not ok
        print(f"  {'✅' if ok else '❌'} {entrada!r} → {sale!r}")
    for archivo in ("data/cartelera.json", "data/cartelera-madrid.json"):
        p = Path(__file__).parent / archivo
        filas = json.loads(p.read_text(encoding="utf-8"))["screenings"]
        malos = sorted({f["ciclo"] for f in filas if gritado(f.get("ciclo") or "")})
        fallos += bool(malos)
        print(f"  {'✅' if not malos else '❌'} {archivo}: ciclos en mayúsculas {malos or 'ninguno'}")
    print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
