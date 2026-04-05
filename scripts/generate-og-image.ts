/**
 * Generate the OG image (1200×630) by screenshotting an HTML template.
 *
 * Usage:
 *   bun scripts/generate-og-image.ts
 */

import { chromium } from "@playwright/test";
import { readFileSync, statSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.resolve(__dirname, "../public");
const LOGO_SVG = readFileSync(path.join(PUBLIC, "logo.svg"), "utf-8");
const FONT_DIR = path.join(PUBLIC, "fonts");
const OUTPUT = path.join(PUBLIC, "og-image.png");

const WIDTH = 1200;
const HEIGHT = 630;

const HTML = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@font-face {
  font-family: 'Assistant';
  font-weight: 200 800;
  src: url('file://${FONT_DIR}/assistant-latin.woff2') format('woff2');
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  width: ${WIDTH}px;
  height: ${HEIGHT}px;
  background: #080d1a;
  background-image: radial-gradient(ellipse 80% 60% at 50% 50%, rgba(0,99,209,0.12) 0%, transparent 70%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-family: 'Assistant', system-ui, -apple-system, sans-serif;
  gap: 28px;
  overflow: hidden;
}

.logo {
  width: 110px;
  height: 110px;
}

.logo svg {
  width: 100%;
  height: 100%;
}

.title {
  color: #f0f0f0;
  font-size: 72px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.tagline {
  color: rgba(255, 255, 255, 0.55);
  font-size: 40px;
  font-weight: 400;
  letter-spacing: 0.01em;
}
</style>
</head>
<body>
  <div class="logo">${LOGO_SVG}</div>
  <div class="title">Wanderbound</div>
  <div class="tagline">Turn your Polarsteps trips into photo albums</div>
</body>
</html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
await page.setContent(HTML, { waitUntil: "networkidle" });
await page.screenshot({ path: OUTPUT, type: "png" });
await browser.close();

const kb = Math.round(statSync(OUTPUT).size / 1024);
console.log(`Wrote ${OUTPUT} (${kb}KB)`);
