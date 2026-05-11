#!/usr/bin/env python3
"""
Genera las PNGs del posteo de Instagram para una fecha dada, usando la
página instagram.html renderizada headless con playwright.

Uso:
    python3 scripts/generate_posts.py                  # hoy, portrait, todos los cines
    python3 scripts/generate_posts.py --date 2026-05-12
    python3 scripts/generate_posts.py --format square

Output: posts/YYYY-MM-DD/slide-1.png, slide-2.png, ...
"""
import argparse
import asyncio
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date as date_cls
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextmanager
def static_server(root: Path, port: int):
    """Levanta `python -m http.server` en background y lo apaga al salir."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "--bind", "127.0.0.1", str(port)],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Esperar a que el server esté arriba
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    try:
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


async def generate(date_str: str, cine: str = "all", fmt: str = "portrait") -> list[Path]:
    from playwright.async_api import async_playwright

    out_dir = HERE / "posts" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    # Limpiar PNGs previos para este día
    for old in out_dir.glob("*.png"):
        old.unlink()

    port = _free_port()
    saved: list[Path] = []
    with static_server(HERE, port):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 2000},
                device_scale_factor=2,
            )
            page = await ctx.new_page()
            url = (
                f"http://127.0.0.1:{port}/instagram.html"
                f"?date={date_str}&cine={cine}&format={fmt}"
            )
            await page.goto(url, wait_until="networkidle", timeout=20000)
            # Esperar nuestro marker de render terminado
            await page.wait_for_function("document.body.dataset.ready === 'true'", timeout=10000)
            # Anular el auto-scale para capturar a tamaño real
            await page.evaluate("""
                document.getElementById('stage').style.transform = 'scale(1)';
                document.getElementById('stage').style.height = 'auto';
                document.body.style.overflow = 'visible';
            """)
            total = await page.evaluate("window.cartelera.totalSlides()")
            print(f"  {date_str} {fmt} {cine!r}: {total} slide(s)")

            for i in range(1, int(total) + 1):
                await page.evaluate(f"window.cartelera.setSlide({i})")
                # El re-render reaplicaba el scale; volver a anular
                await page.evaluate("""
                    document.getElementById('stage').style.transform = 'scale(1)';
                    document.getElementById('stage').style.height = 'auto';
                """)
                await page.wait_for_timeout(400)
                post_el = await page.query_selector("#post")
                out = out_dir / f"slide-{i}.png"
                await post_el.screenshot(path=str(out), type="png", omit_background=False)
                saved.append(out)
                print(f"    ✓ {out.relative_to(HERE)}")
            await browser.close()
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date_cls.today().isoformat(),
                        help="YYYY-MM-DD (default: hoy)")
    parser.add_argument("--cine", default="all",
                        help="'all' o nombre exacto del cine (default: all)")
    parser.add_argument("--format", default="portrait",
                        choices=["portrait", "square", "story"],
                        help="formato de slide (default: portrait)")
    args = parser.parse_args()

    saved = asyncio.run(generate(args.date, args.cine, args.format))
    if saved:
        print(f"\n✅ {len(saved)} slide(s) → posts/{args.date}/")
    else:
        print(f"\n⚠️  no se generó ningún slide para {args.date}")
        sys.exit(1)


if __name__ == "__main__":
    main()
