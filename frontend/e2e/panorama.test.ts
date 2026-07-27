import type { Page } from "@playwright/test";
import { expect, openEditor, scrollToStep, test } from "./fixtures";
import { mockAlbum, mockStep, TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");
const panoramaName = "wide.jpg";

async function mockPanoramaAlbum(page: Page) {
  let media = {
    uid: 1,
    aid: "aid-1",
    name: panoramaName,
    kind: "photo",
    width: 4000,
    height: 1000,
    byte_size: 4096,
    panorama_candidate: true,
    panorama: null,
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
    panorama_candidate: false,
  };
  const album = {
    ...mockAlbum,
    safe_margin_mm: 10,
    hidden_headers: [
      "cover-back" as const,
      "overview" as const,
      "full-map" as const,
    ],
    chapters: [
      {
        ...mockAlbum.chapters[0],
        step_ids: [step.id],
        front_cover_photo: coverMedia.name,
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
      if (route.request().method() === "DELETE") {
        media = { ...media, panorama: null };
        await route.fulfill({ json: media });
        return;
      }
      const body = route.request().postDataJSON() as Record<string, number>;
      appliedFrame = body;
      media = {
        ...media,
        panorama: body,
        updated_at: "2026-07-26T12:00:00Z",
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

test("frames a panorama globally and prints a two-page spread", async ({
  authedPage: page,
}) => {
  await page.setViewportSize({ width: 1440, height: 760 });
  const state = await mockPanoramaAlbum(page);
  await openEditor(page);
  await scrollToStep(page, "Amsterdam");

  const treat = page
    .locator(`[data-media="${panoramaName}"]`)
    .locator(".panorama-frame-action");
  await expect(treat).toBeVisible({ timeout: 5_000 });
  const [buttonBox, imageBox] = await Promise.all([
    treat.boundingBox(),
    page.locator(`[data-media="${panoramaName}"]`).boundingBox(),
  ]);
  expect(buttonBox!.x + buttonBox!.width / 2).toBeLessThan(
    imageBox!.x + imageBox!.width / 2,
  );
  await treat.click();
  const dialog = page.locator(".panorama-dialog");
  await expect(dialog).toBeVisible();
  await expect
    .poll(() =>
      dialog.evaluate(
        (element) => element.scrollHeight <= element.clientHeight,
      ),
    )
    .toBe(true);
  const preview = dialog.locator(".panorama-viewport");
  await expect(preview).toBeVisible();
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.locator('input[name="zoom"]')).toHaveAttribute("max", "2");

  await dialog.locator('input[name="perspective"]').fill("55");
  await dialog.locator('input[name="zoom"]').fill("1.837");
  await expect(
    dialog.locator('input[name="zoom"]').locator("..").locator("output"),
  ).toHaveText("1.84×");
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

  await dialog.locator(".apply-button").click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => state.appliedFrame()).not.toBeNull();
  expect(state.appliedFrame()).toMatchObject({
    perspective_fov: 55,
    zoom: 1.837,
  });
  expect(Math.abs(state.appliedFrame()!.yaw)).toBeGreaterThan(1);

  await expect(page.locator('img[src*="/panorama-render"]')).toHaveCount(1);
  const fullPagePanorama = page
    .locator(`[data-media="${panoramaName}"]`)
    .first();
  await expect
    .poll(() =>
      fullPagePanorama.evaluate((element) => {
        const container = element.parentElement;
        const image = element.querySelector("img");
        return {
          padding: container ? getComputedStyle(container).paddingTop : null,
          fit: image ? getComputedStyle(image).objectFit : null,
        };
      }),
    )
    .toEqual({ padding: "0px", fit: "cover" });
  await scrollToStep(page, "Amsterdam");
  await expect(page.locator(".panorama-frame-action").first()).toBeVisible();
  await page.locator(".panorama-spread-action").click();
  await expect.poll(() => state.step().pages[0]?.kind).toBe("panorama_spread");
  await expect(page.locator(".alignment-item")).toHaveCount(1);
  await expect(page.locator(".panorama-page")).toHaveCount(2);
  await expect(page.locator(".alignment-item").getByRole("note")).toBeVisible();

  await page.goto("/print/aid-1", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".panorama-page")).toHaveCount(2);
  await expect(page.locator(".alignment-item")).toHaveCount(1);
  await expect(
    page.locator(".alignment-item").getByRole("note"),
  ).toHaveCount(0);
  await expect(page.locator(".panorama-frame-action")).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as Record<string, boolean>).__PRINT_READY__ ===
          true,
      ),
    )
    .toBe(true);

  await openEditor(page);
  await page.locator(".panorama-disable-action").first().click();
  await expect(page.locator('img[src*="/panorama-render"]')).toHaveCount(0);
});
