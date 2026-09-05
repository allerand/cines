#!/usr/bin/env python3
"""
Test de los candados que evitan postear dos veces el mismo día a Instagram.

    python3 test_ig_no_duplicar.py

El 5/9/2026 las stories con las funciones del día salieron DOS VECES en
@sitedigocine. La causa: post-ig.yml tiene cuatro crons (porque el scheduler de
GitHub llega tarde o no llega) y se apoyaba en la marca posts/<fecha>/.posteado-
para que sólo el primero publique — pero la marca se escribe al FINAL, después
de los ~10 minutos que tarda el posteo. Ese día GitHub soltó la cola de golpe,
dos corridas arrancaron casi juntas (marcas 14:05:31Z y 14:14:50Z, contra crons
de 11:08-12:43 UTC), las dos vieron el directorio sin marca y las dos postearon.

Los candados que se prueban acá:

  1. El lock atómico: crear un ref en el remoto es atómico y cada corrida empuja
     un objeto distinto, así que de dos corridas simultáneas UNA SOLA se lo
     queda. Es el que hubiera evitado el 5/9.
  2. El chequeo contra la Graph API: antes de publicar se le pregunta a la
     cuenta si ya tiene lo del día. Es el único que sigue valiendo si el repo
     miente (marca borrada, corrida a mano desde otra máquina).
  3. El contrato de códigos de salida, que es lo que decide si un fallo se
     reintenta (nada publicado) o no se reintenta nunca (algo ya salió).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts"))

import post_to_instagram as ig  # noqa: E402

HOY = "2026-09-05"
fallos = 0


def chequear(nombre, ok, detalle=None):
    global fallos
    print(f"  {'✓' if ok else '✗'} {nombre}")
    if not ok:
        fallos += 1
        if detalle is not None:
            print(f"      {detalle}")


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


# ---------------------------------------------------------------------------
# 1. El lock atómico del workflow
# ---------------------------------------------------------------------------

def test_lock_atomico():
    print("\nEl lock: dos corridas simultáneas, una sola postea")
    ref = "refs/tags/ig-posted/2026-09-06/stories-only"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        git("init", "-q", "--bare", "server.git", cwd=tmp)
        origen = tmp / "server.git"

        corridas = []
        for nombre in ("runA", "runB"):
            d = tmp / nombre
            d.mkdir()
            git("init", "-q", "-b", "main", str(d), cwd=tmp)
            git("config", "user.email", "bot@x", cwd=d)
            git("config", "user.name", "bot", cwd=d)
            if nombre == "runA":
                (d / "f.txt").write_text("hola\n")
                git("add", "f.txt", cwd=d)
                git("commit", "-qm", "base", cwd=d)
                git("remote", "add", "origin", str(origen), cwd=d)
                git("push", "-q", "origin", "main", cwd=d)
            else:
                git("remote", "add", "origin", str(origen), cwd=d)
                git("fetch", "-q", "origin", cwd=d)
                git("checkout", "-qB", "main", "origin/main", cwd=d)
            corridas.append(d)

        # Cada corrida arma su objeto con commit-tree: el mensaje lleva el run
        # id, así que nunca coinciden (si coincidieran, el segundo push sería
        # un no-op exitoso y las dos postearían).
        def reclamar(d, run_id):
            sha = git("commit-tree", "HEAD^{tree}", "-p", "HEAD",
                      "-m", f"ig lock — run {run_id}", cwd=d).stdout.strip()
            hecho = git("push", "origin", f"{sha}:{ref}",
                        cwd=d, check=False).returncode == 0
            return sha, hecho

        shaA, tomoA = reclamar(corridas[0], "111")
        shaB, tomoB = reclamar(corridas[1], "222")
        chequear("las dos corridas arman objetos distintos", shaA != shaB)
        chequear("exactamente una se queda con el lock",
                 [tomoA, tomoB].count(True) == 1, (tomoA, tomoB))

        # commit-tree no puede ensuciar la rama: si el claim quedara como commit
        # de main, el push de las slides se lo llevaría puesto.
        sucio = git("status", "--porcelain", cwd=corridas[0]).stdout.strip()
        chequear("el claim no toca HEAD ni el working tree", sucio == "", sucio)

        existe = git("ls-remote", "origin", ref, cwd=corridas[0]).stdout.strip()
        chequear("ls-remote ve el lock (distingue conflicto de error de red)",
                 bool(existe), existe)

        # rc=3 = no se publicó nada: se suelta y el próximo cron reintenta.
        git("push", "-q", "origin", f":{ref}", cwd=corridas[0])
        _, retoma = reclamar(corridas[1], "333")
        chequear("soltado el lock, la corrida siguiente puede tomarlo", retoma)


# ---------------------------------------------------------------------------
# 2. El chequeo contra Instagram
# ---------------------------------------------------------------------------

def test_chequeo_instagram():
    print("\nEl chequeo contra la cuenta: qué se considera 'ya posteado'")

    def stories(*timestamps):
        return {"data": [{"id": str(i), "timestamp": t}
                         for i, t in enumerate(timestamps)]}

    def con(respuesta):
        def fake_get(edge, params):
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta
        ig.api_get = fake_get

    con(stories("2026-09-05T11:30:00+0000"))
    chequear("una story de hoy frena el posteo",
             ig._publicado_el("stories", HOY, "1", "tok") == 1)

    con(stories("2026-09-04T23:00:00+0000"))
    chequear("una story de ayer (sigue viva, 24h) no frena nada",
             ig._publicado_el("stories", HOY, "1", "tok") == 0)

    # Buenos Aires es UTC-3: la medianoche del día siguiente son las 03:00Z.
    con(stories("2026-09-06T02:59:00+0000"))
    chequear("23:59 de Buenos Aires todavía es hoy",
             ig._publicado_el("stories", HOY, "1", "tok") == 1)
    con(stories("2026-09-06T03:00:00+0000"))
    chequear("00:00 de Buenos Aires ya es mañana",
             ig._publicado_el("stories", HOY, "1", "tok") == 0)

    con(RuntimeError("GET → 400: (#100) missing permission"))
    chequear("si no se puede preguntar devuelve None, que NO es cero",
             ig._publicado_el("stories", HOY, "1", "tok") is None)


# ---------------------------------------------------------------------------
# 3. El contrato de códigos de salida
# ---------------------------------------------------------------------------

def test_codigos_de_salida():
    print("\nLos códigos de salida: cuándo se reintenta y cuándo no")
    R = ig.Resultado
    casos = [
        ("posteo limpio → 0",                    R(publicados=14), [], 0),
        ("ya estaba posteado → 0 (marca el día)", R(ya_estaban=True), [], 0),
        ("no había slides → 3 (reintentable)",   R(), [], 3),
        ("falló sin publicar nada → 3",          R(fallidos=3), [], 3),
        ("falló ANTES de publicar → 3",          R(), [RuntimeError("boom")], 3),
        ("falló DESPUÉS de publicar → 1 (no reintentar: duplicaría)",
                                                 R(publicados=5, fallidos=2), [], 1),
        ("dry-run nunca pide reintento",         R(), [], 0),
    ]
    for nombre, res, errs, esperado in casos:
        dry = "dry-run" in nombre
        got = ig._codigo_de_salida(res, errs, dry)
        chequear(f"{nombre}", got == esperado, f"dio {got}")


def main():
    test_lock_atomico()
    test_chequeo_instagram()
    test_codigos_de_salida()
    print(f"\n{'TODO OK' if not fallos else f'{fallos} casos fallando'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
