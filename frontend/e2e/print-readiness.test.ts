import { expect, test } from "./fixtures";
import {
  mockAlbum,
  mockStep,
  TINY_JPEG_BASE64,
} from "../tests/fixtures/mocks";

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");

test("waits for panorama spread images before signaling print readiness", async ({
  authedPage,
}) => {
  const media = {
    uid: 1,
    aid: "aid-1",
    name: "wide.jpg",
    kind: "photo",
    width: 4000,
    height: 1000,
    byte_size: 4096,
    panorama: {
      status: "active" as const,
      detection: "dimensions" as const,
      source_width: 4000,
      source_height: 1000,
      captured_fov: 180,
      revision: 7,
    },
  };
  const album = {
    ...mockAlbum,
    hidden_headers: [
      "cover-front",
      "cover-back",
      "overview",
      "full-map",
    ],
    media: [media],
  };
  const steps = [
    {
      ...mockStep,
      pages: [{ kind: "panorama_spread" as const, media: [media.name] }],
    },
  ];

  await authedPage.route(
    "**/api/v1/albums/aid-1/print-bundle*",
    (route) =>
      route.fulfill({
        json: { album, steps, segments: [], total_distance_km: 0 },
      }),
  );

  let releaseImage!: () => void;
  const imageGate = new Promise<void>((resolve) => {
    releaseImage = resolve;
  });
  let imageRequested = false;
  await authedPage.route("**/media/wide.jpg*", async (route) => {
    imageRequested = true;
    await imageGate;
    await route.fulfill({ contentType: "image/jpeg", body: mediaBody });
  });

  try {
    await authedPage.goto("/print/aid-1", { waitUntil: "domcontentloaded" });
    await expect(authedPage.locator(".panorama-page")).toHaveCount(2);
    await expect.poll(() => imageRequested).toBe(true);
    await authedPage.evaluate(() => document.fonts.ready);
    await authedPage.waitForTimeout(1_000);

    expect(
      await authedPage.evaluate(
        () =>
          (window as unknown as Record<string, boolean>).__PRINT_READY__ ===
          true,
      ),
    ).toBe(false);
  } finally {
    releaseImage();
  }

  await expect
    .poll(() =>
      authedPage.evaluate(
        () =>
          (window as unknown as Record<string, boolean>).__PRINT_READY__ ===
          true,
      ),
    )
    .toBe(true);
});
