/**
 * Generate landing page screenshots from the running app.
 *
 * Prerequisites:
 *   - Backend + frontend dev servers running (mise run dev:backend & mise run dev:frontend)
 *   - A user logged in with real trip data (photos, hike maps, videos)
 *
 * Usage:
 *   bun scripts/landing-screenshots.ts
 *
 * Captures each screenshot in both dark and light mode variants.
 * Each is saved as both .jpg and .webp in public/landing/.
 * Screenshots that can't be taken (e.g., no hike map in data) are skipped.
 */

import { chromium, type Page, type Locator } from "@playwright/test";
import sharp from "sharp";
import { readdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT = path.resolve(__dirname, "../public/landing");
const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const JPEG_QUALITY = 90;
const WEBP_QUALITY = 80;
const LOAD_WAIT = 3000;
const MODES = ["dark", "light"] as const;

// ---------------------------------------------------------------------------

async function main() {
  const browser = await chromium.launch({ headless: true });

  try {
    for (const mode of MODES) {
      console.log(`\n=== ${mode} mode ===`);
      const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
        deviceScaleFactor: 2,
        colorScheme: mode,
      });
      const page = await context.newPage();

      try {
        await navigateToEditor(page);
        await captureEditor(page, mode);
        await captureAutoAlbum(page, mode);
        await captureHikeMap(page, mode);
        await captureVideoPoster(page, mode);
        await captureLocalization(page, mode);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  await convertToWebP();
  console.log("\nDone! Screenshots saved to public/landing/");
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

async function navigateToEditor(page: Page) {
  console.log("Navigating to editor...");
  await page.goto(`${BASE}/editor`, { waitUntil: "networkidle" });
  await page.waitForSelector(".album-container", { timeout: 15_000 });

  // Dismiss onboarding banners
  for (const btn of await page.locator(".got-it").all()) {
    if (await btn.isVisible()) await btn.click();
  }

  // Wait for lazy sections, images, and map tiles to load
  await page.waitForTimeout(LOAD_WAIT);
}

async function waitForImages(page: Page, scope?: Locator) {
  const root = scope ?? page.locator("body");
  await root.evaluate((el) =>
    Promise.all(
      Array.from(el.querySelectorAll<HTMLImageElement>("img"))
        .filter((img) => !img.complete)
        .map(
          (img) =>
            new Promise<void>((resolve) => {
              img.onload = img.onerror = () => resolve();
            }),
        ),
    ),
  );
}

function save(name: string, mode: string) {
  return path.join(OUTPUT, `${name}-${mode}.jpg`);
}

// ---------------------------------------------------------------------------
// Screenshot captures
// ---------------------------------------------------------------------------

/** Full editor viewport — header, toolbar, step page visible. */
async function captureEditor(page: Page, mode: string) {
  // Scroll past the cover page to show a step page
  const firstStep = page.locator(".step-entry").first();
  if ((await firstStep.count()) > 0) {
    await firstStep.scrollIntoViewIfNeeded();
    // Scroll up a bit so the header + step are both visible
    await page.evaluate(() => window.scrollBy(0, -60));
    await page.waitForTimeout(500);
  }

  await page.screenshot({ path: save("editor", mode), type: "jpeg", quality: JPEG_QUALITY });
  console.log(`  ✓ editor-${mode}.jpg`);
}

/** Close-up of a photo grid page (step page with 3+ photos). */
async function captureAutoAlbum(page: Page, mode: string) {
  const pages = page.locator(".step-entry .page-container");
  const count = await pages.count();

  for (let i = 0; i < count; i++) {
    const container = pages.nth(i);
    const mediaCount = await container.locator("[data-media]").count();
    if (mediaCount >= 3) {
      await container.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await waitForImages(page, container);
      await container.screenshot({ path: save("auto-album", mode), type: "jpeg", quality: JPEG_QUALITY });
      console.log(`  ✓ auto-album-${mode}.jpg`);
      return;
    }
  }
  console.warn(`  ⚠ No step page with 3+ photos found — skipping auto-album-${mode}.jpg`);
}

/** Hike map page with elevation profile. */
async function captureHikeMap(page: Page, mode: string) {
  const hikeMaps = page.locator(".map-wrapper:has(.elevation-profile)");
  if ((await hikeMaps.count()) === 0) {
    console.warn(`  ⚠ No hike map found — skipping hike-map-${mode}.jpg`);
    return;
  }

  const hike = hikeMaps.first();
  await hike.scrollIntoViewIfNeeded();

  // Wait for mapbox tiles to render
  try {
    await hike.locator("[data-map]").first().waitFor({ state: "attached", timeout: 5000 });
    await page.waitForFunction(
      () => document.querySelector(".map-wrapper:has(.elevation-profile) [data-map]")?.hasAttribute("data-map-ready"),
      { timeout: 10_000 },
    );
  } catch {
    console.warn("    Map tiles may not be fully loaded — proceeding anyway");
  }
  await page.waitForTimeout(1000);

  // Screenshot the inner page-container (not the wrapper with editor chrome)
  const pageContainer = hike.locator(".page-container").first();
  await pageContainer.screenshot({ path: save("hike-map", mode), type: "jpeg", quality: JPEG_QUALITY });
  console.log(`  ✓ hike-map-${mode}.jpg`);
}

/** Video in playing state with "Use as poster" frame bar. */
async function captureVideoPoster(page: Page, mode: string) {
  // Find a media item that contains a video
  const videoItems = page.locator("[data-media]:has(video), [data-media]:has(.play-overlay)");
  if ((await videoItems.count()) === 0) {
    console.warn(`  ⚠ No video found — skipping video-poster-${mode}.jpg`);
    return;
  }

  const item = videoItems.first();
  await item.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);

  // Click the play overlay to start the video
  const playOverlay = item.locator(".play-overlay");
  if ((await playOverlay.count()) > 0) {
    await playOverlay.click();
    // Wait for video to start and frame bar to appear
    await item.locator(".frame-bar").waitFor({ state: "visible", timeout: 5000 });
    await page.waitForTimeout(500);
  }

  await item.screenshot({ path: save("video-poster", mode), type: "jpeg", quality: JPEG_QUALITY });
  console.log(`  ✓ video-poster-${mode}.jpg`);

  // Pause the video to avoid interfering with later screenshots
  await page.keyboard.press("Escape");
}

/** Step page in Hebrew (RTL) — demonstrates localization. */
async function captureLocalization(page: Page, mode: string) {
  // Fetch current user data, then replay with Hebrew locale
  let userData: Record<string, unknown>;
  try {
    userData = await page.evaluate(async () => {
      const resp = await fetch("/api/v1/users", { credentials: "include" });
      return resp.json() as Promise<Record<string, unknown>>;
    });
  } catch {
    console.warn(`  ⚠ Could not fetch user data — skipping localization-${mode}.jpg`);
    return;
  }

  // Intercept user API to return Hebrew locale
  await page.route("**/api/v1/users", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: { ...userData, locale: "he_IL" } });
    }
    return route.continue();
  });

  // Reload to trigger locale switch
  await navigateToEditor(page);

  // Find a step page with text content (description visible)
  const stepPages = page.locator(".step-entry .page-container");
  const count = await stepPages.count();
  let target: Locator | null = null;

  for (let i = 0; i < count; i++) {
    const container = stepPages.nth(i);
    // Look for a page with both a photo and description text
    const hasMedia = (await container.locator("[data-media]").count()) > 0;
    const hasText = (await container.locator(".editable-text").count()) > 0;
    if (hasMedia && hasText) {
      target = container;
      break;
    }
  }

  if (!target) {
    // Fall back to any step page
    if (count > 0) target = stepPages.first();
  }

  if (target) {
    await target.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await waitForImages(page, target);
    await target.screenshot({ path: save("localization", mode), type: "jpeg", quality: JPEG_QUALITY });
    console.log(`  ✓ localization-${mode}.jpg`);
  } else {
    console.warn(`  ⚠ No step page found — skipping localization-${mode}.jpg`);
  }

  // Restore normal user API
  await page.unroute("**/api/v1/users");
}

// ---------------------------------------------------------------------------
// WebP conversion
// ---------------------------------------------------------------------------

async function convertToWebP() {
  console.log("\nConverting to WebP...");
  const files = await readdir(OUTPUT);
  for (const file of files.filter((f) => f.endsWith(".jpg"))) {
    const src = path.join(OUTPUT, file);
    const dest = src.replace(/\.jpg$/, ".webp");
    await sharp(src).webp({ quality: WEBP_QUALITY }).toFile(dest);
    console.log(`  ${file} → ${file.replace(/\.jpg$/, ".webp")}`);
  }
}

// ---------------------------------------------------------------------------

main().catch((err) => {
  console.error("Screenshot generation failed:", err);
  process.exit(1);
});
