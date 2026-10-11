#!/usr/bin/env python3
"""
Arma en _site/ lo que se publica en sitedigo.com (GitHub Pages).

    python3 scripts/build_site.py [--out _site]

Copia los archivos versionados del repo menos los que lista .assetsignore, que
es la misma lista que usaba el Worker de Cloudflare: el código del scraper, el
cache y los logs no son para el público. Así hay un solo lugar donde decir qué
se sirve y qué no.

.assetsignore tiene sintaxis de .gitignore. Acá se entiende lo que usamos: un
patrón sin barra (`*.py`) vale para el nombre del archivo en cualquier carpeta;
uno con barra (`data/cache.json`, `.git/**`) se compara contra la ruta entera.
"""
import argparse
import fnmatch
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patrones() -> list[str]:
    with open(os.path.join(RAIZ, ".assetsignore"), encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def ignorado(ruta: str, pats: list[str]) -> bool:
    for pat in pats:
        if "/" in pat.rstrip("/"):
            if fnmatch.fnmatch(ruta, pat.lstrip("/")):
                return True
        elif fnmatch.fnmatch(os.path.basename(ruta), pat):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(RAIZ, "_site"))
    args = ap.parse_args()

    archivos = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, check=True,
                              capture_output=True, text=True).stdout.split("\0")
    pats = patrones()
    publicar = [a for a in archivos if a and not ignorado(a, pats)]

    shutil.rmtree(args.out, ignore_errors=True)
    total = 0
    for a in publicar:
        destino = os.path.join(args.out, a)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(os.path.join(RAIZ, a), destino)
        total += os.path.getsize(destino)

    if "index.html" not in publicar:
        print("✗ index.html quedó afuera: revisá .assetsignore", file=sys.stderr)
        return 1
    print(f"{len(publicar)} archivos, {total / 1e6:.1f} MB en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
