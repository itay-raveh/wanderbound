import { expect, test } from "./fixtures";
import { mockAlbum, mockMedia, mockSteps } from "../tests/fixtures/mocks";

test("cover preview preserves the chapter targeted by spine edits", async ({
  authedPage: page,
}) => {
  const steps = [mockSteps[0], { ...mockSteps[0], id: 2 }];
  const album = {
    ...mockAlbum,
    cover_bleed_mm: 0,
    hidden_headers: ["overview", "full-map"],
    chapters: [
      { ...mockAlbum.chapters[0], spine_width_mm: 1 },
      {
        ...mockAlbum.chapters[0],
        id: "chapter-2",
        title: "Second chapter",
        step_ids: [2],
        spine_width_mm: 22,
      },
    ],
  };
  await page.route("**/api/v1/albums/aid-1", async (route) => {
    if (route.request().method() === "PATCH")
      Object.assign(album, route.request().postDataJSON());
    await route.fulfill({ json: album });
  });
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: steps }),
  );
  await page.route("**/api/v1/albums/aid-1/media", (route) =>
    route.fulfill({
      json: mockMedia.map((media) => ({
        ...media,
        panorama_candidate: media.name === "cover.jpg",
      })),
    }),
  );
  await page.goto("/editor");
  await page
    .getByRole("button", { name: "Expand", exact: true })
    .filter({ hasText: "Second chapter" })
    .click();
  const secondCover = page.locator(
    '[data-nav-section="chapter-chapter-2-cover-front"]',
  );
  await secondCover.click();
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(1000);
  await page.getByRole("button", { name: 'Expand "Print"' }).click();
  const spine = page.getByLabel("Spine width", { exact: true });
  await expect(spine).toHaveValue("22");
  const cover = page
    .locator(".page-container")
    .filter({
      has: page.locator(".front-title", { hasText: "Second chapter" }),
    });
  await cover.locator(".panorama-frame-action").click({ trial: true });

  await page
    .locator(".page-container")
    .filter({
      has: page.locator(".front-title", { hasText: "Second chapter" }),
    })
    .getByRole("button", { name: "Preview wraparound cover" })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Preview wraparound cover",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".front-title")).toHaveText("Second chapter");
  await expect(dialog.locator(".cover-background img")).toHaveCount(2);
  await dialog.getByLabel("Spine width", { exact: true }).fill("24");
  await dialog.getByLabel("Cover bleed", { exact: true }).fill("6");
  await expect
    .poll(() => album.chapters.map((chapter) => chapter.spine_width_mm))
    .toEqual([1, 24]);
  await expect.poll(() => album.cover_bleed_mm).toBe(6);
  await expect
    .poll(() =>
      dialog.locator(".page-container").evaluate((el) => {
        const rect = el.getBoundingClientRect();
        return rect.width / rect.height;
      }),
    )
    .toBeCloseTo((594 + 24 + 12) / (210 + 12), 2);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(1000);
  await expect(spine).toHaveValue("24");
  await page
    .locator(".page-container")
    .filter({
      has: page.locator(".front-title", { hasText: "Second chapter" }),
    })
    .getByRole("button", { name: "Preview wraparound cover" })
    .click();
  await expect(dialog.locator(".front-title")).toHaveText("Second chapter");
  await expect(dialog.getByLabel("Cover bleed", { exact: true })).toHaveValue(
    "6",
  );
  await expect(dialog.getByLabel("Spine width", { exact: true })).toHaveValue(
    "24",
  );
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page
    .getByRole("button", { name: "Expand", exact: true })
    .filter({ hasText: "South America" })
    .click();
  await page
    .locator('[data-nav-section="chapter-chapter-1-cover-front"]')
    .click();
  await expect(spine).toHaveValue("1");
  await page
    .locator(".page-container")
    .filter({ has: page.locator(".front-title", { hasText: "South America" }) })
    .getByRole("button", { name: "Preview wraparound cover" })
    .click();
  await expect(dialog.locator(".front-title")).toHaveText("South America");
  await page.setViewportSize({ width: 1024, height: 768 });
  await expect
    .poll(() =>
      dialog
        .locator(".preview-dialog")
        .evaluate(
          (el) => el.getBoundingClientRect().width <= window.innerWidth,
        ),
    )
    .toBe(true);
  await expect(
    dialog.getByRole("button", { name: "Close", exact: true }),
  ).toBeInViewport();
  await page.screenshot({
    path: "../output/issue228-print/shared-cover-dialog.png",
  });
});

test("exports trim-sized interiors and a separate wraparound cover with bleed", async ({
  authedPage: page,
}, testInfo) => {
  test.setTimeout(90_000);
  const album = {
    ...mockAlbum,
    safe_margin_mm: 5,
    interior_bleed_mm: 3,
    cover_bleed_mm: 4,
    hidden_headers: ["overview", "full-map"],
    chapters: [{ ...mockAlbum.chapters[0], spine_width_mm: 12 }],
    media: [
      ...mockMedia,
      { name: "back.jpg", width: 1920, height: 1080, byte_size: 4096 },
    ],
  };
  const steps = mockSteps.map((step) => ({
    ...step,
    weather: { ...step.weather, day: { ...step.weather.day, icon: "snow" } },
    pages: [{ kind: "panorama_spread", media: ["photo2.jpg"] }],
  }));
  await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album,
        steps,
        segments: [],
        total_distance_km: 0,
      },
    }),
  );
  await page.route("**/media/**", (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900"><rect width="1600" height="900" fill="${route.request().url().includes("back.jpg") ? "#315a62" : "#976138"}"/><circle cx="800" cy="450" r="240" fill="#dfcdb0"/></svg>`,
    }),
  );
  await page.emulateMedia({ media: "print" });
  for (const [part, width, height] of [
    ["content", 303, 216],
    ["cover", 614, 218],
  ] as const) {
    await page.goto(
      `/print/aid-1?part=${part}&chapter=${album.chapters[0].id}`,
    );
    await page.waitForFunction(
      () =>
        (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
    );
    if (part === "cover")
      await expect(page.locator(".page-container")).toHaveCount(1);
    else {
      await expect(page.locator(".cover-sheet")).toHaveCount(0);
      await expect(page.locator(".page-container")).toHaveCount(4);
      await expect(page.locator(".step-main")).toHaveCSS("display", "flex");
      await expect(page.locator(".alignment-artwork")).toHaveCSS(
        "display",
        "flex",
      );
    }
    const dimensions = await page
      .locator(".page-container")
      .first()
      .evaluate((el) => {
        const rect = el.getBoundingClientRect();
        return [(rect.width * 25.4) / 96, (rect.height * 25.4) / 96];
      });
    expect(dimensions[0]).toBeCloseTo(width, 1);
    expect(dimensions[1]).toBeCloseTo(height, 1);
    if (part === "cover") {
      const photos = page.locator(".cover-background img");
      await expect(photos).toHaveCount(2);
      const decoded = await photos.evaluateAll((images) =>
        images.every((image) => {
          const img = image as HTMLImageElement;
          return img.complete && img.naturalWidth > 1 && img.naturalHeight > 1;
        }),
      );
      expect(decoded).toBe(true);
    }
    const pdf = await page.pdf({
      path: testInfo.outputPath(`${part}.pdf`),
      preferCSSPageSize: true,
      printBackground: true,
    });
    const boxes = [
      ...pdf
        .toString("latin1")
        .matchAll(/\/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]/g),
    ];
    expect(boxes.length).toBeGreaterThan(0);
    for (const box of boxes) {
      expect(Math.abs((Number(box[1]) * 25.4) / 72 - width)).toBeLessThan(0.4);
      expect(Math.abs((Number(box[2]) * 25.4) / 72 - height)).toBeLessThan(0.4);
    }
    expect(boxes).toHaveLength(await page.locator(".page-container").count());
    if (part === "cover") {
      const back = await page
        .locator(".wrap-back .cover-background")
        .boundingBox();
      const front = await page
        .locator(".wrap-front .cover-background")
        .boundingBox();
      const sheet = await page.locator(".page-container").boundingBox();
      expect(Math.abs(back!.x - sheet!.x)).toBeLessThan(1);
      expect(Math.abs(back!.x + back!.width - front!.x)).toBeLessThan(1);
      expect(
        Math.abs(front!.x + front!.width - sheet!.x - sheet!.width),
      ).toBeLessThan(1);
    }
  }
  await page.goto(`/print/aid-1?part=combined&chapter=${album.chapters[0].id}`);
  await page.waitForFunction(
    () =>
      (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
  );
  const combined = await page.pdf({
    path: testInfo.outputPath("combined.pdf"),
    preferCSSPageSize: true,
    printBackground: true,
  });
  const boxes = [
    ...combined
      .toString("latin1")
      .matchAll(/\/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]/g),
  ];
  expect(boxes).toHaveLength(await page.locator(".page-container").count());
  for (const [index, box] of boxes.entries()) {
    const width = index < 2 ? 305 : 303;
    const height = index < 2 ? 218 : 216;
    expect(Math.abs((Number(box[1]) * 25.4) / 72 - width)).toBeLessThan(0.4);
    expect(Math.abs((Number(box[2]) * 25.4) / 72 - height)).toBeLessThan(0.4);
  }
  album.hidden_headers.push("cover-back");
  await page.goto(`/print/aid-1?part=content&chapter=${album.chapters[0].id}`);
  await page.waitForFunction(
    () =>
      (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
  );
  await expect(page.locator(".page-container")).toHaveCount(4);
  await expect(page.locator(".panorama-page")).toHaveCount(2);
  album.hidden_headers = album.hidden_headers.filter(
    (key) => key !== "overview",
  );
  steps[0].pages = [{ kind: "grid", media: ["photo2.jpg"] }];
  await page.goto(`/print/aid-1?part=content&chapter=${album.chapters[0].id}`);
  await page.waitForFunction(
    () =>
      (window as unknown as Record<string, unknown>).__PRINT_READY__ === true,
  );
  await expect(page.locator(".overview")).toHaveCSS("display", "flex");
  await expect(page.locator(".page-artwork.page")).toHaveCSS("display", "flex");
  const overviewFill = await page
    .locator(".overview-content")
    .evaluate(
      (el) =>
        el.getBoundingClientRect().height /
        el.parentElement!.getBoundingClientRect().height,
    );
  expect(overviewFill).toBeGreaterThan(0.95);
  await page.pdf({
    path: testInfo.outputPath("layout.pdf"),
    preferCSSPageSize: true,
    printBackground: true,
  });
});
