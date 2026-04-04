/**
 * Generate landing page screenshots from a live backend with demo data.
 *
 * Prerequisites:
 *   - Backend running (mise run dev:backend)
 *   - Frontend running (mise run dev:frontend)
 *   - Database migrated (mise run migrate)
 *
 * Usage:
 *   bun run screenshots
 */

import { chromium, type Browser, type Locator, type Page } from "@playwright/test";
import { mkdir, readdir, writeFile } from "fs/promises";
import path from "path";
import sharp from "sharp";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT = path.resolve(__dirname, "../public/landing");
const FRONTEND = process.env.BASE_URL ?? "http://localhost:5173";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const API = `${BACKEND}/api/v1`;
const JPEG_QUALITY = 90;
const WEBP_QUALITY = 80;
const WEBP_WIDTHS = [640, 1536];
const EDGE_TRIM = 4; // device pixels to crop from each edge (2 CSS px at 2× scale)
const MODES = ["dark", "light"] as const;

/** Album customization applied after processing. */
const ALBUM_OVERRIDES = {
  title: "South America",
  subtitle: "Adventure of a lifetime!",
};

// ---------------------------------------------------------------------------
// Demo lifecycle — create, process, customize, clean up
// ---------------------------------------------------------------------------

interface DemoSession {
  cookie: string;
  albumId: string;
  userId: number;
}

async function createDemo(lang?: string): Promise<DemoSession> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (lang) headers["Accept-Language"] = lang;

  const resp = await fetch(`${API}/users/demo`, { method: "POST", headers });
  if (!resp.ok) throw new Error(`POST /users/demo failed: ${resp.status}`);

  const setCookie = resp.headers.get("set-cookie");
  if (!setCookie) throw new Error("No session cookie in demo response");
  const match = setCookie.match(/session=[^;]+/);
  if (!match) throw new Error("Could not parse session cookie");
  const cookie = match[0];

  const data = await resp.json();
  const albumId = data.trips[0].id;
  const userId = data.user.id;
  console.log(`  Demo user ${userId} created (album: ${albumId})`);
  return { cookie, albumId, userId };
}

async function waitForProcessing(session: DemoSession): Promise<void> {
  console.log("  Processing demo data...");
  const resp = await fetch(`${API}/users/process`, {
    headers: { Cookie: session.cookie, Accept: "text/event-stream" },
  });
  if (!resp.ok) throw new Error(`GET /users/process failed: ${resp.status}`);
  if (!resp.body) throw new Error("No body in SSE response");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    if (text.includes('"type":"error"') || text.includes("event: error")) {
      throw new Error("Processing failed — error event received");
    }
  }
  console.log("  Processing complete");
}

async function customizeAlbum(
  session: DemoSession,
  overrides: Record<string, unknown>,
): Promise<void> {
  const resp = await fetch(`${API}/albums/${session.albumId}`, {
    method: "PATCH",
    headers: {
      Cookie: session.cookie,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(overrides),
  });
  if (!resp.ok) throw new Error(`PATCH album failed: ${resp.status}`);
}

async function deleteDemo(session: DemoSession): Promise<void> {
  await fetch(`${API}/users/demo`, {
    method: "DELETE",
    headers: { Cookie: session.cookie },
  }).catch(() => {}); // Best effort
  console.log(`  Demo user ${session.userId} cleaned up`);
}

// ---------------------------------------------------------------------------
// Playwright context & navigation
// ---------------------------------------------------------------------------

async function withContext(
  browser: Browser,
  mode: string,
  session: DemoSession,
  fn: (page: Page) => Promise<void>,
) {
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    colorScheme: mode as "dark" | "light",
  });
  await context.addCookies([
    {
      name: "session",
      value: session.cookie.replace("session=", ""),
      domain: new URL(FRONTEND).hostname,
      path: "/",
    },
  ]);
  context.setDefaultTimeout(60_000);
  try {
    await fn(await context.newPage());
  } finally {
    await context.close();
  }
}

async function navigateToPrint(page: Page, albumId: string, mode: string) {
  const dark = mode === "dark" ? "?dark=true" : "";
  console.log(`  Navigating to print view (${mode})...`);

  await page.addInitScript(() => {
    setInterval(() => {
      document.querySelectorAll("[data-map]:not([data-map-ready])").forEach((el) => {
        (el as HTMLElement).dataset.mapReady = "";
      });
    }, 500);
  });

  await page.goto(`${FRONTEND}/print/${albumId}${dark}`, {
    waitUntil: "load",
    timeout: 30_000,
  });

  await page.waitForSelector(".album-container", { timeout: 30_000 });
  console.log("  Album container found, waiting for content to settle...");
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
          .map(
            (img) =>
              new Promise<void>((r) => {
                img.onload = img.onerror = () => r();
              }),
          ),
      ),
    ),
    new Promise<void>((r) => setTimeout(r, timeoutMs)),
  ]);
}

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

async function captureAutoAlbum(page: Page, mode: string) {
  // Target a 1P+2L mixed page — the most visually interesting layout for the showcase.
  const mixed = page.locator(".page-container:has(.layout-1p-2l)").first();
  if ((await mixed.count()) > 0) {
    await waitForImages(mixed);
    const hasLoadedImage = await mixed.evaluate((el) =>
      Array.from(el.querySelectorAll<HTMLImageElement>("img")).some(
        (img) => img.naturalWidth > 0,
      ),
    );
    if (hasLoadedImage) {
      await captureElement(page, mixed, save("auto-album", mode));
      console.log(`  ✓ auto-album-${mode}.jpg`);
      return;
    }
  }
  console.warn(
    `  ⚠ No 1P+2L page with loaded photos — skipping auto-album-${mode}.jpg`,
  );
}

async function captureHikeMap(page: Page, mode: string) {
  const hike = page.locator(".page-container:has(.elevation-overlay)").first();
  if ((await hike.count()) === 0) {
    console.warn(`  ⚠ No hike map found — skipping hike-map-${mode}.jpg`);
    return;
  }
  await Promise.race([
    page.waitForFunction(
      () =>
        (
          document
            .querySelector(".elevation-overlay svg path")
            ?.getAttribute("d")?.length ?? 0
        ) > 10,
    ),
    page.waitForTimeout(15_000),
  ]).catch(() => console.warn("    Elevation profile may not be loaded"));
  await page.waitForTimeout(1000);
  await captureElement(page, hike, save("hike-map", mode));
  console.log(`  ✓ hike-map-${mode}.jpg`);
}

async function captureStepPage(page: Page, mode: string, name = "step-page") {
  const stepMain = page.locator(".page-container.step-main").first();
  if ((await stepMain.count()) === 0) {
    console.warn(`  ⚠ No step main page found — skipping ${name}-${mode}.jpg`);
    return;
  }
  await waitForImages(stepMain);
  await captureElement(page, stepMain, save(name, mode));
  console.log(`  ✓ ${name}-${mode}.jpg`);
}

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
        sharp(src)
          .webp({ quality: WEBP_QUALITY })
          .toFile(path.join(OUTPUT, `${base}.webp`))
          .then(() => console.log(`  ${base}.webp`)),
        ...WEBP_WIDTHS.map((w) =>
          sharp(src)
            .resize(w)
            .webp({ quality: WEBP_QUALITY })
            .toFile(path.join(OUTPUT, `${base}-${w}w.webp`))
            .then(() => console.log(`  ${base}-${w}w.webp`)),
        ),
      ];
    }),
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  await mkdir(OUTPUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  // --- English demo ---
  console.log("\n=== Creating English demo ===");
  const enSession = await createDemo("en");
  try {
    await waitForProcessing(enSession);
    await customizeAlbum(enSession, ALBUM_OVERRIDES);

    for (const mode of MODES) {
      console.log(`\n=== ${mode} mode ===`);
      await withContext(browser, mode, enSession, async (page) => {
        await navigateToPrint(page, enSession.albumId, mode);
        await captureCover(page, mode);
        await captureAutoAlbum(page, mode);
        await captureHikeMap(page, mode);
        await captureStepPage(page, mode);
        await captureOverview(page, mode);
      });
    }
  } finally {
    await deleteDemo(enSession);
  }

  // --- Hebrew demo (localization screenshot) ---
  console.log("\n=== Creating Hebrew demo ===");
  const heSession = await createDemo("he");
  try {
    await waitForProcessing(heSession);

    for (const mode of MODES) {
      console.log(`\n=== ${mode} mode (Hebrew) ===`);
      await withContext(browser, mode, heSession, async (page) => {
        await navigateToPrint(page, heSession.albumId, mode);
        await captureStepPage(page, mode, "localization");
      });
    }
  } finally {
    await deleteDemo(heSession);
  }

  await browser.close();
  await convertToWebP();
  console.log("\nDone! Screenshots saved to public/landing/");
}

main().catch((err) => {
  console.error("Screenshot generation failed:", err);
  process.exit(1);
});
