import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import asyncio
import json
from dataclasses import asdict
from playwright.async_api import async_playwright

from scraper import scrape_lugones


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        screenings = await scrape_lugones(page)

        await browser.close()

    print(f"\nTotal Lugones: {len(screenings)} funciones\n")

    for s in screenings:
        if "marilyn" in s.title.lower() or s.cine == "Sala Lugones":
            print(json.dumps(asdict(s), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
