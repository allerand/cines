#!/usr/bin/env python3
"""Backfill de original_title en data/cartelera.json desde data/cache.json.

run.py ya escribe original_title en corridas nuevas; este script completa el
JSON existente sin re-scrapear. Match por URL de Letterboxd (unívoco) y, si no,
por título (title_es / title_en contra la key del cache y su title_en).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARTELERA = ROOT / "data" / "cartelera.json"
CACHE = ROOT / "data" / "cache.json"


def norm(t: str) -> str:
    return (t or "").strip().lower()


def main() -> None:
    cartelera = json.loads(CARTELERA.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))

    by_url: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for key, meta in cache.items():
        if not isinstance(meta, dict):
            continue
        orig = (meta.get("original_title") or "").strip()
        if not orig:
            continue
        if meta.get("url"):
            by_url[meta["url"]] = orig
        by_title.setdefault(norm(key), orig)
        if meta.get("title_en"):
            by_title.setdefault(norm(meta["title_en"]), orig)
        if meta.get("title_es"):
            by_title.setdefault(norm(meta["title_es"]), orig)

    filled = had = missed = 0
    for s in cartelera.get("screenings", []):
        if s.get("original_title"):
            had += 1
            continue
        orig = by_url.get(s.get("letterboxd") or "") \
            or by_title.get(norm(s.get("title_es"))) \
            or by_title.get(norm(s.get("title_en")))
        if orig:
            s["original_title"] = orig
            filled += 1
        else:
            s["original_title"] = ""
            missed += 1

    CARTELERA.write_text(
        json.dumps(cartelera, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"✅ backfill: {filled} completadas, {had} ya tenían, {missed} sin dato")


if __name__ == "__main__":
    main()
