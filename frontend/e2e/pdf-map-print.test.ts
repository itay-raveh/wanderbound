import type { Page } from "@playwright/test";

import type { PrintBundle, Segment, StepRead } from "../src/client";
import {
  mockAlbum,
  mockMedia,
  mockStep,
  mockUser,
  TINY_JPEG_BASE64,
} from "../tests/fixtures/mocks";
import { expect, test } from "./fixtures";

const API = "**/api/v1";

const BASEMAP_COLOR = [20, 107, 58] as const;
const OVERVIEW_ROUTE_COLOR = [74, 144, 217] as const;
const HIKE_ROUTE_COLOR = [231, 124, 49] as const;

const secondStep: StepRead = {
  ...mockStep,
  id: 2,
  name: "Utrecht",
  timestamp: 1704070800,
  datetime: "2024-01-01T13:00:00+01:00",
  location: {
    ...mockStep.location,
    name: "Utrecht",
    detail: "Utrecht",
    lat: 52.09,
    lon: 5.12,
  },
  cover: null,
  pages: [],
};

const hike: Segment = {
  uid: 1,
  aid: "aid-1",
  start_time: mockStep.timestamp,
  end_time: secondStep.timestamp,
  kind: "hike",
  timezone_id: "Europe/Amsterdam",
  points: [
    { lat: 52.37, lon: 4.89, time: mockStep.timestamp },
    { lat: 52.24, lon: 5.0, time: 1704069000 },
    { lat: 52.09, lon: 5.12, time: secondStep.timestamp },
  ],
  route: null,
};

const bundle: PrintBundle = {
  album: {
    ...mockAlbum,
    show_page_numbers: true,
    hidden_headers: ["cover-front", "cover-back", "overview"],
    maps_ranges: [["2024-01-01", "2024-01-01"]],
    chapters: [
      {
        ...mockAlbum.chapters[0],
        step_ids: [mockStep.id, secondStep.id],
      },
    ],
    media: mockMedia,
  },
  steps: [mockStep, secondStep],
  segments: [hike],
  total_distance_km: 0,
};

const BASEMAP_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEAAQMAAABmvDolAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURRRrOv///0zqgckAAAABYktHRAH/Ai3eAAAAB3RJTUUH6ggeDQgXuG9ltQAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyNi0wOC0zMFQxMzowODoyMyswMDowMGSJqt8AAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjYtMDgtMzBUMTM6MDg6MjMrMDA6MDAV1BJjAAAAKHRFWHRkYXRlOnRpbWVzdGFtcAAyMDI2LTA4LTMwVDEzOjA4OjIzKzAwOjAwQsEzvAAAAB9JREFUaN7twQENAAAAwqD3T20ON6AAAAAAAAAAAL4NIQAAAX8ZnKcAAAAASUVORK5CYII=",
  "base64",
);
const TERRAIN_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEAAQMAAABmvDolAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGUExURQGGoP///x1IEE8AAAABYktHRAH/Ai3eAAAAB3RJTUUH6ggeDQgXuG9ltQAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyNi0wOC0zMFQxMzowODoyMyswMDowMGSJqt8AAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjYtMDgtMzBUMTM6MDg6MjMrMDA6MDAV1BJjAAAAKHRFWHRkYXRlOnRpbWVzdGFtcAAyMDI2LTA4LTMwVDEzOjA4OjIzKzAwOjAwQsEzvAAAAB9JREFUaN7twQENAAAAwqD3T20ON6AAAAAAAAAAAL4NIQAAAX8ZnKcAAAAASUVORK5CYII=",
  "base64",
);

async function installPdfMapFixture(
  page: Page,
  tileDelayMs: number | null = null,
  printBundle = bundle,
) {
  await page.route(`${API}/config`, (route) =>
    route.fulfill({ json: { MAPBOX_TOKEN: "test-token" } }),
  );
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route(`${API}/albums/*/print-bundle*`, (route) =>
    route.fulfill({ json: printBundle }),
  );
  await page.route(`${API}/albums/*/segments/points*`, (route) =>
    route.fulfill({ json: printBundle.segments }),
  );
  let fullMediaRequests = 0;
  await page.route(`${API}/albums/*/media/*`, (route) => {
    if (!new URL(route.request().url()).searchParams.has("w"))
      fullMediaRequests++;
    return route.fulfill({
      contentType: "image/jpeg",
      body: Buffer.from(TINY_JPEG_BASE64, "base64"),
    });
  });

  let tileRequested = false;
  let tileFulfilled = false;
  let releaseTiles = () => {};
  const tileGate =
    tileDelayMs === null
      ? new Promise<void>((resolve) => {
          releaseTiles = resolve;
        })
      : null;
  await page.route("**/e2e-map/**/*.png", async (route) => {
    tileRequested = true;
    if (tileGate) await tileGate;
    else if (tileDelayMs > 0)
      await new Promise((resolve) => setTimeout(resolve, tileDelayMs));
    await route.fulfill({
      contentType: "image/png",
      body: BASEMAP_TILE,
    });
    tileFulfilled = true;
  });
  await page.route("**/e2e-dem/**/*.png", (route) =>
    route.fulfill({
      contentType: "image/png",
      body: TERRAIN_TILE,
    }),
  );
  await page.route("**/styles/v1/mapbox/standard-satellite*", (route) =>
    route.fulfill({
      json: {
        version: 8,
        sources: {
          basemap: {
            type: "raster",
            tiles: [`${new URL(page.url()).origin}/e2e-map/{z}/{x}/{y}.png`],
            tileSize: 256,
            maxzoom: 14,
          },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#202020" },
          },
          {
            id: "basemap",
            type: "raster",
            source: "basemap",
            paint: { "raster-fade-duration": 1_500 },
          },
        ],
      },
    }),
  );
  await page.route("**/v4/mapbox.mapbox-terrain-dem-v1.json*", (route) =>
    route.fulfill({
      json: {
        tilejson: "2.2.0",
        tiles: [`${new URL(page.url()).origin}/e2e-dem/{z}/{x}/{y}.png`],
        minzoom: 0,
        maxzoom: 14,
      },
    }),
  );
  await page.route("**/map-sessions/v1*", (route) =>
    route.fulfill({ status: 204 }),
  );

  await page.emulateMedia({ media: "print" });
  return {
    tileRequested: () => tileRequested,
    tileFulfilled: () => tileFulfilled,
    fullMediaRequests: () => fullMediaRequests,
    releaseTiles,
  };
}

async function releasePrintMapMemory(page: Page) {
  await page.waitForFunction(() => {
    const record = window as unknown as Record<string, unknown>;
    return (
      document
        .querySelector(".print-view")
        ?.getAttribute("data-print-phase") === "map-memory" ||
      Boolean(record.__PRINT_ERROR__)
    );
  });
  if (
    await page.evaluate(() =>
      Boolean((window as unknown as Record<string, unknown>).__PRINT_ERROR__),
    )
  )
    return;

  await page.requestGC();
  await page.evaluate(() => {
    (
      window as unknown as Record<string, unknown>
    ).__PRINT_MAP_MEMORY_RELEASED__ = true;
  });
}

async function snapshotColorCounts(page: Page) {
  return page.locator(".mapbox-print-snapshot").evaluateAll(
    async (images, targets) => {
      const results: number[][] = [];
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("2D canvas is unavailable");

      for (const image of images) {
        const snapshot = image as HTMLCanvasElement | HTMLImageElement;
        if (snapshot instanceof HTMLImageElement) await snapshot.decode();
        const sourceWidth =
          snapshot instanceof HTMLCanvasElement
            ? snapshot.width
            : snapshot.naturalWidth;
        const sourceHeight =
          snapshot instanceof HTMLCanvasElement
            ? snapshot.height
            : snapshot.naturalHeight;
        const scale = Math.min(1, 1_000 / sourceWidth);
        canvas.width = Math.round(sourceWidth * scale);
        canvas.height = Math.round(sourceHeight * scale);
        context.drawImage(snapshot, 0, 0, canvas.width, canvas.height);
        const pixels = context.getImageData(
          0,
          0,
          canvas.width,
          canvas.height,
        ).data;
        const counts = targets.map(() => 0);
        for (let i = 0; i < pixels.length; i += 4) {
          targets.forEach((target, index) => {
            if (
              Math.abs(pixels[i] - target[0]) <= 12 &&
              Math.abs(pixels[i + 1] - target[1]) <= 12 &&
              Math.abs(pixels[i + 2] - target[2]) <= 12
            ) {
              counts[index]++;
            }
          });
        }
        results.push(counts);
      }
      canvas.width = 0;
      canvas.height = 0;
      return results;
    },
    [BASEMAP_COLOR, OVERVIEW_ROUTE_COLOR, HIKE_ROUTE_COLOR],
  );
}

test.describe("PDF map snapshots", () => {
  test.describe.configure({ timeout: 120_000 });

  test("renders a restored drive after reload without fitting distant flights", async ({
    authedPage: page,
  }) => {
    const driving: Segment = {
      ...hike,
      kind: "driving",
      route: [],
    };
    // Distant incoming/outgoing flights must not change destination-pin framing.
    const flights: Segment[] = [
      {
        ...hike,
        kind: "flight",
        start_time: mockStep.timestamp - 3600,
        end_time: mockStep.timestamp,
        points: [
          { lat: 40.7, lon: -74, time: mockStep.timestamp - 3600 },
          hike.points[0],
        ],
      },
      {
        ...hike,
        kind: "flight",
        start_time: secondStep.timestamp,
        end_time: secondStep.timestamp + 3600,
        points: [
          hike.points.at(-1)!,
          { lat: 40.7, lon: -74, time: secondStep.timestamp + 3600 },
        ],
      },
    ];
    await installPdfMapFixture(page, 0, {
      ...bundle,
      album: { ...bundle.album, maps_ranges: [] },
      segments: [driving, ...flights],
    });
    for (let attempt = 0; attempt < 2; attempt++) {
      if (attempt === 0) await page.goto("/print/aid-1");
      else await page.reload();
      await releasePrintMapMemory(page);
      await page.waitForFunction(
        () =>
          (window as unknown as Record<string, unknown>).__PRINT_READY__ ===
          true,
      );
      // Inspect real WebGL pixels in the existing whole-trip map.
      // An empty saved route draws no line; the recovered GPS drive spans
      // both sides of the map despite terrain and the captured JPEG encoding.
      const extent = await page
        .locator(".map-page .mapbox-print-snapshot")
        .last()
        .evaluate(async (image) => {
          const snapshot = image as HTMLImageElement;
          await snapshot.decode();
          const canvas = document.createElement("canvas");
          canvas.width = snapshot.naturalWidth;
          canvas.height = snapshot.naturalHeight;
          const context = canvas.getContext("2d")!;
          context.drawImage(snapshot, 0, 0);
          const pixels = context.getImageData(
            0,
            0,
            canvas.width,
            canvas.height,
          ).data;
          let minY = canvas.height;
          let maxY = 0;
          for (let y = 0; y < canvas.height; y++) {
            for (let x = 0; x < canvas.width; x++) {
              const i = (y * canvas.width + x) * 4;
              if (
                pixels[i] > 190 &&
                pixels[i + 1] > 190 &&
                pixels[i + 2] > 190
              ) {
                minY = Math.min(minY, y);
                maxY = Math.max(maxY, y);
              }
            }
          }
          return (maxY - minY) / canvas.height;
        });
      expect(extent).toBeGreaterThan(0.5);
      if (attempt === 1)
        await page
          .locator(".map-page")
          .last()
          .screenshot({
            path: test.info().outputPath("saved-route-restored.png"),
          });
    }
  });

  test("keeps maps visible in the screen spread preview after capture", async ({
    authedPage: page,
  }) => {
    test.slow();
    await installPdfMapFixture(page, 0);
    await page.addInitScript(() => {
      const active = new Set<string>();
      const create = URL.createObjectURL.bind(URL);
      const revoke = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = (blob) => {
        const url = create(blob);
        if (blob instanceof Blob && blob.type === "image/jpeg") active.add(url);
        return url;
      };
      URL.revokeObjectURL = (url) => {
        active.delete(url);
        revoke(url);
      };
      Object.assign(window, { activeMapSnapshots: active });
    });
    const liveSnapshots = () =>
      page.evaluate(
        () =>
          (window as unknown as { activeMapSnapshots: Set<string> })
            .activeMapSnapshots.size,
      );
    let failRoutes = true;
    await page.route(`${API}/albums/*/segments/points*`, (route) =>
      failRoutes
        ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
        : route.fulfill({ json: [hike] }),
    );
    await page.emulateMedia({ media: "screen" });
    await page.route(`${API}/albums/aid-1`, (route) =>
      route.fulfill({ json: bundle.album }),
    );
    await page.route(`${API}/albums/aid-1/steps`, (route) =>
      route.fulfill({ json: bundle.steps }),
    );
    await page.route(`${API}/albums/aid-1/segments`, (route) =>
      route.fulfill({ json: bundle.segments }),
    );
    await page.goto("/editor");
    const originalPixelRatio = await page.evaluate(
      () => window.devicePixelRatio,
    );
    await page
      .getByRole("button", { name: "Print preview", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Print preview",
      exact: true,
    });
    await expect(dialog.locator("[data-map]")).toHaveCount(2);
    await dialog
      .getByRole("button", { name: "Next spread", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "Previous spread", exact: true })
      .click();
    await expect(
      dialog.locator('[data-map-error="content-load-failed"]'),
    ).toHaveCount(2, { timeout: 30_000 });
    await expect.poll(liveSnapshots).toBe(0);
    failRoutes = false;
    await dialog
      .getByRole("button", { name: "Retry map", exact: true })
      .first()
      .click();
    await dialog
      .getByRole("button", { name: "Retry map", exact: true })
      .click();
    await expect(
      dialog.getByText("Loading map…", { exact: true }).first(),
    ).toBeVisible();
    const snapshots = dialog.locator(
      "[data-map-snapshot-ready] > .mapbox-print-snapshot",
    );
    await expect(snapshots).toHaveCount(2, { timeout: 120_000 });
    await expect(dialog.locator(".mapboxgl-canvas")).toHaveCount(0);
    await expect(dialog.locator(".map-status")).toHaveCount(0);
    await expect.poll(liveSnapshots).toBe(2);
    for (const snapshot of await snapshots.all()) {
      await expect(snapshot).toBeVisible();
      const fillsMap = await snapshot.evaluate((image) => {
        const bounds = image.getBoundingClientRect();
        const parent = image.parentElement!.getBoundingClientRect();
        return (
          Math.abs(bounds.width - parent.width) < 1 &&
          Math.abs(bounds.height - parent.height) < 1
        );
      });
      expect(fillsMap).toBe(true);
    }
    const capturedUrls = await snapshots.evaluateAll((images) =>
      images.map((image) => (image as HTMLImageElement).src),
    );
    await dialog
      .getByRole("button", { name: "Next spread", exact: true })
      .click();
    await expect(snapshots).toHaveCount(0);
    await expect.poll(liveSnapshots).toBe(2);
    await dialog
      .getByRole("button", { name: "Previous spread", exact: true })
      .click();
    await expect(snapshots).toHaveCount(2);
    expect(
      await snapshots.evaluateAll((images) =>
        images.map((image) => (image as HTMLImageElement).src),
      ),
    ).toEqual(capturedUrls);
    await expect(dialog.locator(".mapboxgl-canvas, .map-status")).toHaveCount(
      0,
    );
    await dialog
      .getByRole("button", { name: "Next spread", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "Next spread", exact: true })
      .click();
    await expect.poll(liveSnapshots).toBeLessThan(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect.poll(liveSnapshots).toBe(0);
    expect(await page.evaluate(() => window.devicePixelRatio)).toBe(
      originalPixelRatio,
    );
  });

  test("waits for delayed basemap tiles and runtime routes", async ({
    page,
  }) => {
    const tiles = await installPdfMapFixture(page, null, {
      ...bundle,
      album: {
        ...bundle.album,
        safe_margin_mm: 15,
        interior_bleed_mm: 3,
        hidden_headers: ["cover-front", "cover-back"],
      },
    });

    let releaseRoutes!: () => void;
    const routes = new Promise<void>((resolve) => {
      releaseRoutes = resolve;
    });
    await page.route(`${API}/albums/*/segments/points*`, async (route) => {
      await routes;
      await route.fulfill({ json: [hike] });
    });

    await page.goto("/print/aid-1");
    await expect.poll(tiles.tileRequested, { timeout: 30_000 }).toBe(true);
    expect(tiles.tileFulfilled()).toBe(false);
    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
      ),
    ).not.toBe(true);
    expect(tiles.fullMediaRequests()).toBe(0);
    tiles.releaseTiles();
    const mapMemoryReleased = releasePrintMapMemory(page);

    await expect.poll(tiles.tileFulfilled, { timeout: 30_000 }).toBe(true);
    try {
      await page.waitForTimeout(20_000);
      await expect(page.locator("[data-map-snapshot-ready]")).toHaveCount(0);
    } finally {
      releaseRoutes();
    }

    await page.waitForFunction(
      () => document.querySelectorAll("[data-map-snapshot-ready]").length >= 1,
    );
    expect(tiles.fullMediaRequests()).toBe(0);
    await mapMemoryReleased;

    await page.waitForFunction(
      () =>
        (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
    );
    expect(tiles.fullMediaRequests()).toBeGreaterThan(0);
    await expect(page.locator(".print-view")).toHaveAttribute(
      "data-print-phase",
      "ready",
    );
    expect(tiles.tileFulfilled()).toBe(true);
    const overview = page
      .locator(".page-container")
      .filter({ has: page.locator(".overview") });
    const labels = await overview.locator(".country-labels").boundingBox();
    const number = await overview.locator(".album-page-number").boundingBox();
    expect(labels!.y + labels!.height).toBeLessThan(number!.y);
    const snapshots = page.locator(
      "[data-map][data-map-snapshot-ready] > .mapbox-print-snapshot",
    );
    await expect(snapshots).toHaveCount(2);
    await expect(
      page
        .locator(".page-container")
        .filter({ has: page.locator(".mapbox-print-snapshot") })
        .locator(".album-page-number:visible"),
    ).toHaveCount(2);
    const elevationProfile = page.locator(
      ".hike-map-canvas ~ .elevation-chart svg[role='img']",
    );
    await expect(elevationProfile).toHaveCount(1);
    await expect(elevationProfile.locator("path[stroke]")).toHaveAttribute(
      "d",
      /\S+/,
    );
    const pixelRatios = await snapshots.evaluateAll((images) =>
      images.map((image) => {
        const snapshot = image as HTMLCanvasElement | HTMLImageElement;
        const width =
          snapshot instanceof HTMLCanvasElement
            ? snapshot.width
            : snapshot.naturalWidth;
        return width / image.getBoundingClientRect().width;
      }),
    );
    for (const pixelRatio of pixelRatios) {
      expect(pixelRatio).toBeGreaterThan(1.9);
      expect(pixelRatio).toBeLessThan(2.1);
    }

    const counts = await snapshotColorCounts(page);
    expect(counts[0][0]).toBeGreaterThan(1_000);
    expect(counts[0][1]).toBeGreaterThan(10);
    expect(counts[1][0]).toBeGreaterThan(1_000);
    expect(counts[1][2]).toBeGreaterThan(10);
  });

  test("reports snapshot failure without marking the PDF ready", async ({
    page,
  }) => {
    const tiles = await installPdfMapFixture(page);

    await page.goto("/print/aid-1");
    await expect.poll(tiles.tileRequested, { timeout: 30_000 }).toBe(true);
    await page.evaluate(() => {
      HTMLCanvasElement.prototype.toBlob = (callback) => callback(null);
    });
    tiles.releaseTiles();
    await page.waitForFunction(() =>
      Boolean((window as unknown as Record<string, unknown>).__PRINT_ERROR__),
    );

    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
      ),
    ).toMatchObject({ code: "map-render-failed" });
    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
      ),
    ).not.toBe(true);
    expect(tiles.fullMediaRequests()).toBe(0);
  });

  test("renders maximum trim and bleed maps within the canvas budget", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await installPdfMapFixture(page, 0, {
      ...bundle,
      album: {
        ...bundle.album,
        page_width_mm: 420,
        page_height_mm: 297,
        interior_bleed_mm: 20,
      },
    });
    await page.goto("/print/aid-1");
    await releasePrintMapMemory(page);
    await page.waitForFunction(
      () =>
        (window as unknown as Record<string, unknown>).__PRINT_READY__ ||
        (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
    );
    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
      ),
    ).toBeUndefined();
    await expect(
      page.locator("[data-map][data-map-snapshot-ready]"),
    ).toHaveCount(2);
    expect(
      await page
        .locator(".mapbox-print-snapshot")
        .first()
        .evaluate((el) => (el as HTMLImageElement).naturalWidth),
    ).toBeGreaterThan(3000);
    await expect(page.locator(".mapboxgl-canvas")).toHaveCount(0);
  });

  test("renders every map in one print document without exhausting WebGL contexts", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const manyMapBundle: PrintBundle = {
      ...bundle,
      album: {
        ...bundle.album,
        maps_ranges: Array.from({ length: 18 }, (_, index) => [
          "2024-01-01",
          `2024-01-${String(index + 1).padStart(2, "0")}`,
        ]),
      },
    };
    const consoleMessages: string[] = [];
    page.on("console", (message) => consoleMessages.push(message.text()));
    await installPdfMapFixture(page, 0, manyMapBundle);

    await page.goto("/print/aid-1");
    await releasePrintMapMemory(page);
    const state = await page
      .waitForFunction(() => {
        const record = window as unknown as Record<string, unknown>;
        if (record.__PRINT_READY__ !== true && !record.__PRINT_ERROR__)
          return null;
        return {
          ready: record.__PRINT_READY__ === true,
          error: record.__PRINT_ERROR__ ?? null,
          maps: document.querySelectorAll("[data-map]").length,
          snapshots: document.querySelectorAll(
            "[data-map][data-map-snapshot-ready]",
          ).length,
        };
      })
      .then((result) => result.jsonValue());

    expect(state).toEqual({
      ready: true,
      error: null,
      maps: 19,
      snapshots: 19,
    });

    await expect(page.locator(".album-container")).toHaveAttribute(
      "data-expected-pages",
      "22",
    );
    await expect(
      page.locator("[data-map][data-map-snapshot-ready]"),
    ).toHaveCount(19);
    await expect(page.locator(".mapboxgl-canvas")).toHaveCount(0);
    expect(await page.locator(".map-step-marker").count()).toBeGreaterThan(0);
    expect(
      consoleMessages.some((message) =>
        message.includes("Too many active WebGL contexts"),
      ),
    ).toBe(false);
  });
});
