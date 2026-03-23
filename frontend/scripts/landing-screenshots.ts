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
    // Run 3 contexts per mode in parallel, modes sequentially
    for (const mode of MODES) {
      console.log(`\n=== ${mode} mode ===`);
      await Promise.all([
        withContext(browser, mode, async (page) => {
          await setupMocks(page);
          await navigateToPrint(page, mode);
          await captureAutoAlbum(page, mode);
          await captureHikeMap(page, mode);
        }),
        withContext(browser, mode, async (page) => {
          await setupMocks(page);
          await navigateToEditor(page);
          await captureEditor(page, mode);
          await captureVideoPoster(page, mode);
        }),
        withContext(browser, mode, async (page) => {
          await setupMocks(page, {
            userOverrides: { locale: "he-IL" },
            album: fixtures.hebrewAlbum,
            albumData: fixtures.hebrewAlbumData,
          });
          await navigateToPrint(page, mode);
          await captureLocalization(page, mode);
        }),
      ]);
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
  try {
    await fn(await context.newPage());
  } finally {
    await context.close();
  }
}

async function navigateToEditor(page: Page) {
  console.log("  Navigating to editor...");
  await page.goto(`${BASE}/editor`, { waitUntil: "networkidle" });
  await page.waitForSelector(".album-container", { timeout: 15_000 });
  await page.waitForTimeout(1500);
}

async function navigateToPrint(page: Page, mode: string) {
  const dark = mode === "dark" ? "?dark=true" : "";
  console.log(`  Navigating to print view (${mode})...`);
  await page.goto(`${BASE}/print/${ALBUM_ID}${dark}`, { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => (window as unknown as Record<string, boolean>).__PRINT_READY__ === true,
    { timeout: 30_000 },
  );
  await page.waitForTimeout(500);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Scroll through lazy sections until `selector` appears in the DOM. */
async function scrollToReveal(page: Page, selector: string): Promise<boolean> {
  if ((await page.locator(selector).count()) > 0) return true;

  const lazySections = page.locator(".lazy-placeholder, .lazy-section");
  const total = await lazySections.count();

  for (let i = 0; i < total; i++) {
    try {
      await lazySections.nth(i).scrollIntoViewIfNeeded();
    } catch {
      await page.waitForTimeout(300);
      continue;
    }
    await page.waitForTimeout(500);
    if ((await page.locator(selector).count()) > 0) return true;
  }
  return false;
}

async function waitForImages(scope: Locator) {
  await scope.evaluate((el) =>
    Promise.all(
      Array.from(el.querySelectorAll<HTMLImageElement>("img"))
        .filter((img) => !img.complete)
        .map((img) => new Promise<void>((r) => { img.onload = img.onerror = () => r(); })),
    ),
  );
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

/** Full editor viewport — header, sidebar, Paucartambo step visible. */
async function captureEditor(page: Page, mode: string) {
  await scrollToReveal(page, ".step-entry");
  const firstStep = page.locator(".step-entry").first();
  if ((await firstStep.count()) > 0) {
    await firstStep.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, -60));
    await page.waitForTimeout(500);
  }

  await page.screenshot({ path: save("editor", mode), type: "jpeg", quality: JPEG_QUALITY });
  console.log(`  ✓ editor-${mode}.jpg`);
}

/** Close-up of a 1P+2L photo grid page (print mode — no editor chrome). */
async function captureAutoAlbum(page: Page, mode: string) {
  const pages = page.locator(".page-container");
  const count = await pages.count();

  for (let i = 0; i < count; i++) {
    const container = pages.nth(i);
    if ((await container.locator("[data-media]").count()) >= 3) {
      await waitForImages(container);
      await captureElement(page, container, save("auto-album", mode));
      console.log(`  ✓ auto-album-${mode}.jpg`);
      return;
    }
  }
  console.warn(`  ⚠ No page with 3+ photos — skipping auto-album-${mode}.jpg`);
}

/** Hike map page with elevation profile (print mode). */
async function captureHikeMap(page: Page, mode: string) {
  const hike = page.locator(".page-container:has(.elevation-overlay)").first();
  if ((await hike.count()) === 0) {
    console.warn(`  ⚠ No hike map found — skipping hike-map-${mode}.jpg`);
    return;
  }

  // Wait for elevation profile SVG path to render
  await page.waitForFunction(
    () => (document.querySelector(".elevation-overlay svg path")?.getAttribute("d")?.length ?? 0) > 10,
    { timeout: 15_000 },
  ).catch(() => console.warn("    Elevation profile may not be loaded"));
  await page.waitForTimeout(1000);

  await captureElement(page, hike, save("hike-map", mode));
  console.log(`  ✓ hike-map-${mode}.jpg`);
}

/** Video with frame selection toolbar visible. */
async function captureVideoPoster(page: Page, mode: string) {
  if (!(await scrollToReveal(page, "[data-media] .play-overlay"))) {
    console.warn(`  ⚠ No video found — skipping video-poster-${mode}.jpg`);
    return;
  }

  const playOverlay = page.locator("[data-media] .play-overlay").first();
  const mediaItem = playOverlay.locator("..");
  await mediaItem.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await waitForImages(mediaItem);

  // Click play — triggers video load + photoFocus
  await playOverlay.click();

  // Wait for the video to load its first frame (fixes loading spinner)
  await page.evaluate(() =>
    new Promise<void>((resolve) => {
      const video = document.querySelector<HTMLVideoElement>("[data-media] video");
      if (!video) return resolve();
      if (video.readyState >= 2) return resolve();
      video.addEventListener("loadeddata", () => resolve(), { once: true });
    }),
  );

  // Pause, wait for duration, then seek to mid-point
  await page.evaluate(() => {
    document.querySelector<HTMLVideoElement>("[data-media] video")?.pause();
  });
  // Poll until duration is available (loadedmetadata may have fired before our listener)
  const duration = await page.evaluate(() =>
    new Promise<number>((resolve) => {
      const check = () => {
        const video = document.querySelector<HTMLVideoElement>("[data-media] video");
        if (video && Number.isFinite(video.duration)) return resolve(video.duration);
        requestAnimationFrame(check);
      };
      check();
    }),
  );
  await page.evaluate(
    (t) =>
      new Promise<void>((resolve) => {
        const video = document.querySelector<HTMLVideoElement>("[data-media] video");
        if (!video) return resolve();
        video.addEventListener("seeked", () => resolve(), { once: true });
        video.currentTime = t;
      }),
    duration / 2,
  );
  await page.evaluate(() => {
    document.querySelectorAll(".media-item.focused").forEach((el) => el.classList.remove("focused"));
    (document.activeElement as HTMLElement)?.blur();
  });
  await page.waitForTimeout(500);

  const frameBar = page.locator("[data-media] .frame-bar").first();
  await frameBar.waitFor({ state: "visible", timeout: 5000 });

  const videoItem = page.locator("[data-media]:has(.frame-bar)").first();
  await videoItem.screenshot({ path: save("video-poster", mode), type: "jpeg", quality: JPEG_QUALITY });
  await trimEdges(save("video-poster", mode));
  console.log(`  ✓ video-poster-${mode}.jpg`);
}

/** Step page in Hebrew (RTL) — demonstrates localization (print mode). */
async function captureLocalization(page: Page, mode: string) {
  const target = page.locator(".step-entry .page-container").first();
  if ((await target.count()) === 0) {
    console.warn(`  ⚠ No step page found — skipping localization-${mode}.jpg`);
    return;
  }

  await waitForImages(target);
  await captureElement(page, target, save("localization", mode));
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
