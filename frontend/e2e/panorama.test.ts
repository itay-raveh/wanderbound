import type { Page } from "@playwright/test";
import { expect, openEditor, scrollToStep, test } from "./fixtures";
import { mockAlbum, mockStep, TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");
const panoramaName = "wide.jpg";

function suggestedPanorama() {
  return {
    status: "suggested" as const,
    detection: "dimensions" as const,
    source_width: 4000,
    source_height: 1000,
    captured_fov: 180,
  };
}

async function mockPanoramaAlbum(page: Page) {
  let media = {
    uid: 1,
    aid: "aid-1",
    name: panoramaName,
    kind: "photo",
    width: 4000,
    height: 1000,
    byte_size: 4096,
    panorama: suggestedPanorama(),
  };
  let step = {
    ...mockStep,
    cover: "cover.jpg",
    pages: [{ kind: "grid" as const, media: [panoramaName] }],
    unused: [],
  };
  const coverMedia = {
    uid: 1,
    aid: "aid-1",
    name: "cover.jpg",
    kind: "photo",
    width: 1920,
    height: 1080,
    byte_size: 2048,
  };
  const album = {
    ...mockAlbum,
    hidden_headers: [
      "cover-back" as const,
      "overview" as const,
      "full-map" as const,
    ],
    chapters: [
      {
        ...mockAlbum.chapters[0],
        step_ids: [step.id],
        front_cover_photo: panoramaName,
      },
    ],
  };
  let appliedFrame: Record<string, number> | null = null;

  await page.route("**/api/v1/albums/aid-1", (route) =>
    route.fulfill({ json: album }),
  );
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [step] }),
  );
  await page.route("**/api/v1/albums/aid-1/media", (route) =>
    route.fulfill({ json: [media, coverMedia] }),
  );
  await page.route("**/api/v1/albums/aid-1/media/wide.jpg**", (route) =>
    route.fulfill({ contentType: "image/jpeg", body: mediaBody }),
  );
  await page.route(
    "**/api/v1/albums/aid-1/steps/1/media-layout",
    async (route) => {
      const update = route.request().postDataJSON() as typeof step;
      step = { ...step, ...update };
      await route.fulfill({ json: step });
    },
  );
  await page.route(
    "**/api/v1/albums/aid-1/media/wide.jpg/panorama",
    async (route) => {
      const body = route.request().postDataJSON() as {
        frame: Record<string, number>;
      };
      appliedFrame = body.frame;
      media = {
        ...media,
        panorama: {
          ...media.panorama,
          status: "active",
          ...body.frame,
          revision: 2,
        },
      };
      await route.fulfill({ json: media });
    },
  );
  await page.route("**/api/v1/albums/aid-1/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: { ...album, media: [media, coverMedia] },
        steps: [step],
        segments: [],
        total_distance_km: 0,
      },
    }),
  );

  return {
    appliedFrame: () => appliedFrame,
    step: () => step,
  };
}

test("frames a suggested panorama globally and prints a two-page spread", async ({
  authedPage: page,
}) => {
  const state = await mockPanoramaAlbum(page);
  await openEditor(page);

  const treat = page.getByRole("button", { name: "Treat as panorama" });
  await expect(treat.first()).toBeVisible({ timeout: 5_000 });
  await treat.first().click();
  const dialog = page.getByRole("dialog", { name: "Frame panorama" });
  await expect(dialog).toBeVisible();
  const preview = dialog.getByRole("region", {
    name: "Interactive panorama preview",
  });
  await expect(preview).toBeVisible();
  await expect(dialog.getByRole("alert")).toHaveCount(0);

  await dialog.locator('input[name="perspective"]').fill("55");
  await dialog.locator('input[name="zoom"]').fill("1.8");
  const box = await preview.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width * 0.65, box!.y + box!.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width * 0.35,
    box!.y + box!.height * 0.4,
    {
      steps: 8,
    },
  );
  await page.mouse.up();

  await dialog.getByRole("button", { name: "Apply frame" }).click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => state.appliedFrame()).not.toBeNull();
  expect(state.appliedFrame()).toMatchObject({
    perspective_fov: 55,
    zoom: 1.8,
  });
  expect(Math.abs(state.appliedFrame()!.yaw)).toBeGreaterThan(1);

  await expect(page.locator('img[src*="panorama_revision=2"]')).toHaveCount(2);
  await scrollToStep(page, "Amsterdam");
  await expect(
    page.getByRole("button", { name: "Frame panorama" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Make two-page spread" }).click();
  await expect(
    page.getByText(
      "For the best result, print panorama spreads in a lay-flat photo book.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect.poll(() => state.step().pages[0]?.kind).toBe("panorama_spread");
  await expect(page.locator(".alignment-item")).toHaveCount(1);
  await expect(page.locator(".panorama-page")).toHaveCount(2);

  await page.goto("/print/aid-1", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".panorama-page")).toHaveCount(2);
  await expect(page.locator(".alignment-item")).toHaveCount(1);
  await expect(page.locator(".alignment-help")).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Frame panorama" }),
  ).toHaveCount(0);
});
