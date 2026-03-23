"""Generate the OG image (1200x630) by screenshotting an HTML template with Playwright."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
LOGO_SVG = (ROOT / "frontend" / "public" / "logo.svg").read_text()
OUTPUT = ROOT / "frontend" / "public" / "og-image.png"
FONT_DIR = ROOT / "frontend" / "public" / "fonts"

WIDTH, HEIGHT = 1200, 630

HTML = f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {{
  font-family: 'Inter';
  font-weight: 400;
  src: url('file://{FONT_DIR}/inter-latin.woff2') format('woff2');
}}
@font-face {{
  font-family: 'Inter';
  font-weight: 600;
  src: url('file://{FONT_DIR}/inter-latin.woff2') format('woff2');
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  width: {WIDTH}px;
  height: {HEIGHT}px;
  background: #080d1a;
  background-image: radial-gradient(ellipse 80% 60% at 50% 50%, rgba(0,99,209,0.12) 0%, transparent 70%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  gap: 28px;
  overflow: hidden;
}}

.logo {{
  width: 110px;
  height: 110px;
}}

.logo svg {{
  width: 100%;
  height: 100%;
}}

.title {{
  color: #f0f0f0;
  font-size: 72px;
  font-weight: 600;
  letter-spacing: 0.01em;
}}

.tagline {{
  color: rgba(255, 255, 255, 0.55);
  font-size: 40px;
  font-weight: 400;
  letter-spacing: 0.01em;
}}
</style>
</head>
<body>
  <div class="logo">{LOGO_SVG}</div>
  <div class="title">Wanderbound</div>
  <div class="tagline">Turn your Polarsteps trips into photo albums</div>
</body>
</html>
"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        await page.set_content(HTML, wait_until="networkidle")
        await page.screenshot(path=str(OUTPUT), type="png")
        await browser.close()
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024}KB)")


asyncio.run(main())
