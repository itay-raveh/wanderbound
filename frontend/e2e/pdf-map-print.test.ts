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

async function installPdfMapFixture(page: Page, tileDelayMs = 600) {
  await page.route(`${API}/config`, (route) =>
    route.fulfill({ json: { MAPBOX_TOKEN: "test-token" } }),
  );
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route(`${API}/albums/*/print-bundle*`, (route) =>
    route.fulfill({ json: bundle }),
  );
  await page.route(`${API}/albums/*/segments/points*`, (route) =>
    route.fulfill({ json: [hike] }),
  );
  await page.route(`${API}/albums/*/media/*`, (route) =>
    route.fulfill({
      contentType: "image/jpeg",
      body: Buffer.from(TINY_JPEG_BASE64, "base64"),
    }),
  );

  let tileRequested = false;
  let tileFulfilled = false;
  await page.route("**/e2e-map/**/*.png", async (route) => {
    tileRequested = true;
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
            tiles: ["http://localhost:5173/e2e-map/{z}/{x}/{y}.png"],
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
          { id: "basemap", type: "raster", source: "basemap" },
        ],
      },
    }),
  );
  await page.route("**/v4/mapbox.mapbox-terrain-dem-v1.json*", (route) =>
    route.fulfill({
      json: {
        tilejson: "2.2.0",
        tiles: ["http://localhost:5173/e2e-dem/{z}/{x}/{y}.png"],
        minzoom: 0,
        maxzoom: 14,
      },
    }),
  );

  await page.emulateMedia({ media: "print" });
  return {
    tileRequested: () => tileRequested,
    tileFulfilled: () => tileFulfilled,
  };
}

async function snapshotColorCounts(page: Page) {
  return page.locator(".mapbox-print-snapshot").evaluateAll(
    async (images, targets) =>
      Promise.all(
        images.map(async (image) => {
          const img = image as HTMLImageElement;
          await img.decode();
          const canvas = document.createElement("canvas");
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          const context = canvas.getContext("2d", { willReadFrequently: true });
          if (!context) throw new Error("2D canvas is unavailable");
          context.drawImage(img, 0, 0);
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
          return counts;
        }),
      ),
    [BASEMAP_COLOR, OVERVIEW_ROUTE_COLOR, HIKE_ROUTE_COLOR],
  );
}

test.describe("PDF map snapshots", () => {
  test("waits for delayed basemap tiles and runtime routes", async ({
    page,
  }) => {
    const tiles = await installPdfMapFixture(page);

    await page.goto("/print/aid-1");
    await expect.poll(tiles.tileRequested).toBe(true);
    expect(tiles.tileFulfilled()).toBe(false);
    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
      ),
    ).not.toBe(true);

    await page.waitForFunction(
      () =>
        (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
    );
    expect(tiles.tileFulfilled()).toBe(true);
    const snapshots = page.locator(
      "[data-map][data-map-snapshot-ready] > .mapbox-print-snapshot",
    );
    await expect(snapshots).toHaveCount(2);

    const counts = await snapshotColorCounts(page);
    expect(counts[0][0]).toBeGreaterThan(1_000);
    expect(counts[0][1]).toBeGreaterThan(10);
    expect(counts[1][0]).toBeGreaterThan(1_000);
    expect(counts[1][2]).toBeGreaterThan(10);
  });

  test("reports snapshot failure without marking the PDF ready", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      HTMLCanvasElement.prototype.toDataURL = () => {
        throw new Error("snapshot unavailable");
      };
    });
    await installPdfMapFixture(page, 0);

    await page.goto("/print/aid-1");
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
  });
});
