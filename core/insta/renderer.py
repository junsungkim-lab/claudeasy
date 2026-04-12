"""HTML → PNG rendering via Playwright Chromium."""
from __future__ import annotations


async def render_html_to_png(html: str, width: int = 1080, height: int = 1080) -> bytes:
    """Render an HTML string to PNG bytes using Playwright Chromium."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle", timeout=30_000)
        screenshot: bytes = await page.screenshot(
            type="png",
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        await browser.close()
        return screenshot
