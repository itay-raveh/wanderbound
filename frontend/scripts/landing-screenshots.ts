/**
 * Generate landing page screenshots from the running frontend.
 *
 * Prerequisites:
 *   - Frontend dev server running (bun run dev)
 *   - No backend needed — API responses are mocked with fixture data,
 *     and photos are served from backend/tests/test_data/
 *
 * Usage:
 *   bun run screenshots
 *
 * Captures each screenshot in both dark and light mode variants.
 * Each is saved as both .jpg and .webp in public/landing/.
 */

import { chromium, type Browser, type Locator, type Page, type Route } from "@playwright/test";
import { mkdir, readFile, readdir, writeFile } from "fs/promises";
import path from "path";
import sharp from "sharp";
import { fileURLToPath } from "url";
import fixtures from "./landing-fixtures.json";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT = path.resolve(__dirname, "../public/landing");
const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const JPEG_QUALITY = 90;
const WEBP_QUALITY = 80;
const WEBP_WIDTHS = [640, 1024, 1536];
const EDGE_TRIM = 4; // device pixels to crop from each edge (2 CSS px at 2× scale)
const MODES = ["dark", "light"] as const;

const TRIP_DIR = path.resolve(
  __dirname,
  "../../backend/tests/test_data/trip/south-america-2024-2025_14232450",
);
const ALBUM_ID = fixtures.albumId;

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  await mkdir(OUTPUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  try {
    for (const mode of MODES) {
      console.log(`\n=== ${mode} mode ===`);
      await withContext(browser, mode, async (page) => {
        await setupMocks(page);
        await navigateToPrint(page, mode);
        await captureCover(page, mode);
        await captureAutoAlbum(page, mode);
        await captureHikeMap(page, mode);
        await captureStepPage(page, mode);
        await captureOverview(page, mode);
      });
      // Separate context with Hebrew locale for the localization screenshot
      await withContext(browser, mode, async (page) => {
        await setupMocks(page, {
          userOverrides: { locale: "he-IL" },
          album: fixtures.hebrewAlbum,
          albumData: fixtures.hebrewAlbumData,
        });
        await navigateToPrint(page, mode);
        await captureLocalization(page, mode);
      });
    }
  } finally {
    await browser.close();
  }

  await convertToWebP();
  console.log("\nDone! Screenshots saved to public/landing/");
}

// ---------------------------------------------------------------------------
// Mocks — intercept all backend API calls + serve test media from disk
// ---------------------------------------------------------------------------

interface MockOptions {
  userOverrides?: Record<string, unknown>;
  album?: Record<string, unknown>;
  albumData?: Record<string, unknown>;
}

async function setupMocks(page: Page, opts: MockOptions = {}) {
  const user = { ...fixtures.user, ...opts.userOverrides };
  const album = opts.album ?? fixtures.album;
  const data = opts.albumData ?? fixtures.albumData;

  await page.route("**/api/v1/users", (route) => route.fulfill({ json: user }));

  await page.route("**/api/v1/albums/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/media/")) return handleMedia(route);
    if (url.includes("/data")) return route.fulfill({ json: data });
    if (route.request().method() === "GET") return route.fulfill({ json: album });
    return route.continue();
  });

  await page.addInitScript(() => {
    localStorage.setItem("last-album-id", "sa-2024");
    localStorage.setItem("onboarding-editor-dismissed", "1");
    localStorage.setItem("onboarding-map-dismissed", "1");
  });
}

async function handleMedia(route: Route) {
  const name = route.request().url().split("/media/")[1]?.split("?")[0];
  if (!name) return route.abort();

  const relPath = (fixtures.mediaMap as Record<string, string>)[name];
  if (!relPath) return route.abort();

  const body = await readFile(path.join(TRIP_DIR, relPath));
  const contentType = name.endsWith(".mp4") ? "video/mp4" : "image/jpeg";
  const total = body.length;
  const headers: Record<string, string> = {
    "Accept-Ranges": "bytes",
    "Content-Type": contentType,
  };

  // Support range requests so video seeking works in headless Chromium
  const range = route.request().headers()["range"];
  if (range) {
    const match = range.match(/bytes=(\d+)-(\d*)/);
    if (match) {
      const start = Number(match[1]);
      const end = match[2] ? Number(match[2]) : total - 1;
      headers["Content-Range"] = `bytes ${start}-${end}/${total}`;
      headers["Content-Length"] = String(end - start + 1);
      return route.fulfill({ status: 206, headers, body: body.subarray(start, end + 1) });
    }
  }

  headers["Content-Length"] = String(total);
  return route.fulfill({ status: 200, headers, body });
}

// ---------------------------------------------------------------------------
// Context & navigation
// ---------------------------------------------------------------------------

async function withContext(
  browser: Browser,
  mode: string,
  fn: (page: Page) => Promise<void>,
) {
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    colorScheme: mode as "dark" | "light",
  });
  context.setDefaultTimeout(60_000);
  try {
    await fn(await context.newPage());
  } finally {
    await context.close();
  }
}

async function navigateToPrint(page: Page, mode: string) {
  const dark = mode === "dark" ? "?dark=true" : "";
  console.log(`  Navigating to print view (${mode})...`);

  // Headless Chromium without GPU tile rasterisation may never fire Mapbox
  // "idle" events.  Force data-map-ready on all map elements.
  await page.addInitScript(() => {
    setInterval(() => {
      document.querySelectorAll("[data-map]:not([data-map-ready])").forEach((el) => {
        (el as HTMLElement).dataset.mapReady = "";
      });
    }, 500);
  });

  await page.goto(`${BASE}/print/${ALBUM_ID}${dark}`, { waitUntil: "load", timeout: 30_000 });

  // Wait for the album container, then give content time to render.
  // We don't rely on __PRINT_READY__ because the page-count check blocks
  // when not all pages render in headless Chromium.
  await page.waitForSelector(".album-container", { timeout: 30_000 });
  console.log(`  Album container found, waiting for content to settle...`);
  await page.waitForTimeout(15_000);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function waitForImages(scope: Locator, timeoutMs = 10_000) {
  await Promise.race([
    scope.evaluate((el) =>
      Promise.all(
        Array.from(el.querySelectorAll<HTMLImageElement>("img"))
          .filter((img) => !img.complete)
          .map((img) => new Promise<void>((r) => { img.onload = img.onerror = () => r(); })),
      ),
    ),
    new Promise<void>((r) => setTimeout(r, timeoutMs)),
  ]);
}

/** Crop edge pixels that leak page background into element screenshots. */
async function trimEdges(filePath: string) {
  const meta = await sharp(filePath).metadata();
  if (!meta.width || !meta.height) return;
  const w = meta.width - 2 * EDGE_TRIM;
  const h = meta.height - 2 * EDGE_TRIM;
  if (w <= 0 || h <= 0) return;
  const buf = await sharp(filePath)
    .extract({ left: EDGE_TRIM, top: EDGE_TRIM, width: w, height: h })
    .jpeg({ quality: JPEG_QUALITY })
    .toBuffer();
  await writeFile(filePath, buf);
}

/**
 * Scroll an element into view, wait for Chromium to rasterize it, then capture.
 * Chromium skips rasterization for off-screen elements in long pages, so a plain
 * element.screenshot() on a print-mode page below the fold returns a blank image.
 */
async function captureElement(page: Page, locator: Locator, filePath: string) {
  await locator.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await locator.screenshot({ path: filePath, type: "jpeg", quality: JPEG_QUALITY });
  await trimEdges(filePath);
}

function save(name: string, mode: string) {
  return path.join(OUTPUT, `${name}-${mode}.jpg`);
}

// ---------------------------------------------------------------------------
// Screenshot captures
// ---------------------------------------------------------------------------

/** Front cover page — album title over full-bleed photo (print mode). */
async function captureCover(page: Page, mode: string) {
  const cover = page.locator(".page-container.cover-page").first();
  if ((await cover.count()) === 0) {
    console.warn(`  ⚠ No cover page found — skipping cover-${mode}.jpg`);
    return;
  }

  await waitForImages(cover);
  await captureElement(page, cover, save("cover", mode));
  console.log(`  ✓ cover-${mode}.jpg`);
}

/** Close-up of a 1P+2L photo grid page (print mode — no editor chrome). */
async function captureAutoAlbum(page: Page, mode: string) {
  const pages = page.locator(".page-container");
  const count = await pages.count();

  for (let i = 0; i < count; i++) {
    const container = pages.nth(i);
    if ((await container.locator("[data-media]").count()) >= 3) {
      await waitForImages(container);
      // Skip pages where images failed to load (dummy fixture photos)
      const hasLoadedImage = await container.evaluate((el) =>
        Array.from(el.querySelectorAll<HTMLImageElement>("img"))
          .some((img) => img.naturalWidth > 0),
      );
      if (!hasLoadedImage) continue;
      await captureElement(page, container, save("auto-album", mode));
      console.log(`  ✓ auto-album-${mode}.jpg`);
      return;
    }
  }
  console.warn(`  ⚠ No page with 3+ loaded photos — skipping auto-album-${mode}.jpg`);
}

/** Hike map page with elevation profile (print mode). */
async function captureHikeMap(page: Page, mode: string) {
  const hike = page.locator(".page-container:has(.elevation-overlay)").first();
  if ((await hike.count()) === 0) {
    console.warn(`  ⚠ No hike map found — skipping hike-map-${mode}.jpg`);
    return;
  }

  // Wait for elevation profile SVG path to render
  await Promise.race([
    page.waitForFunction(
      () => (document.querySelector(".elevation-overlay svg path")?.getAttribute("d")?.length ?? 0) > 10,
    ),
    page.waitForTimeout(15_000),
  ]).catch(() => console.warn("    Elevation profile may not be loaded"));
  await page.waitForTimeout(1000);

  await captureElement(page, hike, save("hike-map", mode));
  console.log(`  ✓ hike-map-${mode}.jpg`);
}

/** Step main page with metadata panel — weather, elevation, coordinates (print mode). */
async function captureStepPage(page: Page, mode: string) {
  const stepMain = page.locator(".page-container.step-main").first();
  if ((await stepMain.count()) === 0) {
    console.warn(`  ⚠ No step main page found — skipping step-page-${mode}.jpg`);
    return;
  }

  await waitForImages(stepMain);
  await captureElement(page, stepMain, save("step-page", mode));
  console.log(`  ✓ step-page-${mode}.jpg`);
}

/** Overview page with trip stats — days, distance, photos, countries (print mode). */
async function captureOverview(page: Page, mode: string) {
  const overview = page.locator(".page-container.overview").first();
  if ((await overview.count()) === 0) {
    console.warn(`  ⚠ No overview page found — skipping overview-${mode}.jpg`);
    return;
  }

  await waitForImages(overview);
  await captureElement(page, overview, save("overview", mode));
  console.log(`  ✓ overview-${mode}.jpg`);
}

/** Step page rendered in Hebrew (RTL) to showcase localization support. */
async function captureLocalization(page: Page, mode: string) {
  const stepMain = page.locator(".page-container.step-main").first();
  if ((await stepMain.count()) === 0) {
    console.warn(`  ⚠ No step main page found — skipping localization-${mode}.jpg`);
    return;
  }

  await waitForImages(stepMain);
  await captureElement(page, stepMain, save("localization", mode));
  console.log(`  ✓ localization-${mode}.jpg`);
}

// ---------------------------------------------------------------------------
// WebP conversion
// ---------------------------------------------------------------------------

async function convertToWebP() {
  console.log("\nConverting to WebP...");
  const files = (await readdir(OUTPUT)).filter((f) => f.endsWith(".jpg"));
  await Promise.all(
    files.flatMap((file) => {
      const src = path.join(OUTPUT, file);
      const base = file.replace(/\.jpg$/, "");
      return [
        // Full-size (retina)
        sharp(src).webp({ quality: WEBP_QUALITY }).toFile(path.join(OUTPUT, `${base}.webp`))
          .then(() => console.log(`  ${base}.webp`)),
        // Responsive sizes
        ...WEBP_WIDTHS.map((w) =>
          sharp(src).resize(w).webp({ quality: WEBP_QUALITY }).toFile(path.join(OUTPUT, `${base}-${w}w.webp`))
            .then(() => console.log(`  ${base}-${w}w.webp`)),
        ),
      ];
    }),
  );
}

// ---------------------------------------------------------------------------

main().catch((err) => {
  console.error("Screenshot generation failed:", err);
  process.exit(1);
});
