import asyncio
import json
import sys
from pathlib import Path
from dataclasses import asdict

from playwright.async_api import async_playwright

sys.path.append(str(Path(__file__).resolve().parent.parent))

from scraper import scrape_arthaus


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        screenings = await scrape_arthaus(page, semanas=3)

        await browser.close()

    print(f"\nTotal Arthaus: {len(screenings)} funciones\n")

    for s in screenings:
        print(json.dumps(asdict(s), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
