import { expect, test } from "./fixtures";
import { AlbumMetaSchema } from "../src/client/schemas.gen";
import {
  mockAlbum,
  mockSteps,
  mockMedia,
  mockUser,
} from "../tests/fixtures/mocks";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { readFileSync, readdirSync } from "node:fs";

const artifacts = resolve("../output/playwright/page-size");

test("custom trim dimensions save atomically, survive units/reload and undo, and roll back failures", async ({
  authedPage: page,
}) => {
  test.setTimeout(60_000);
  const album = {
    ...mockAlbum,
    page_width_mm: 297,
    page_height_mm: 210,
    hidden_headers: ["overview", "full-map"],
  };
  const patches: object[] = [];
  let reject = false;
  let releaseFailure = () => {};
  const failureGate = new Promise<void>((done) => {
    releaseFailure = done;
  });
  await page.route("**/api/v1/albums/aid-1", async (route) => {
    if (route.request().method() === "PATCH") {
      const update = route.request().postDataJSON();
      patches.push(update);
      if (reject && "page_width_mm" in update) {
        await failureGate;
        return route.fulfill({
          status: 422,
          json: { detail: "Rejected dimensions" },
        });
      }
      Object.assign(album, update);
    }
    await route.fulfill({ json: album });
  });
  await page.goto("/editor");
  await page.getByRole("button", { name: 'Expand "Print"' }).click();
  const width = page.getByLabel("Width", { exact: true });
  const height = page.getByLabel("Height", { exact: true });
  const apply = page.getByRole("button", { name: "Apply", exact: true });
  await page.locator(".page-size-settings .q-select").click();
  await page.getByRole("option", { name: "US Letter", exact: true }).click();
  await page.getByRole("button", { name: "in", exact: true }).click();
  await expect(width).toHaveValue("11");
  await expect(height).toHaveValue("8.5");
  await page.getByRole("button", { name: "mm", exact: true }).click();
  await page.getByRole("checkbox", { name: "Lock ratio", exact: true }).check();
  await width.fill("300");
  await expect
    .poll(async () => Number(await height.inputValue()))
    .toBeCloseTo((300 * 215.9) / 279.4, 5);
  await page
    .getByRole("checkbox", { name: "Lock ratio", exact: true })
    .uncheck();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await width.fill("300.125");
  await height.fill("220.25");
  await page.getByRole("button", { name: "in", exact: true }).click();
  await page.getByRole("button", { name: "mm", exact: true }).click();
  await expect(width).toHaveValue("300.125");
  await expect(height).toHaveValue("220.25");
  expect(patches).toHaveLength(0);
  await apply.click();
  await expect.poll(() => album.page_width_mm).toBe(300.125);
  expect(patches.at(-1)).toEqual({
    page_width_mm: 300.125,
    page_height_mm: 220.25,
  });
  await expect
    .poll(() =>
      page
        .locator(".page-container")
        .first()
        .evaluate((el) => (parseFloat(getComputedStyle(el).width) * 25.4) / 96),
    )
    .toBeCloseTo(300.125, 2);
  await expect(
    page.getByRole("button", { name: "Undo", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Control+z");
  await expect.poll(() => album.page_width_mm).toBe(297);
  await expect(
    page.getByRole("button", { name: "Redo", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Control+Shift+z");
  await expect.poll(() => album.page_width_mm).toBe(300.125);
  await page.reload();
  await page.getByRole("button", { name: 'Expand "Print"' }).click();
  await expect(width).toHaveValue("300.125");
  await page.locator(".context-panel .q-item").first().click();
  await expect(
    page.locator(".context-panel .q-expansion-item__content"),
  ).toBeHidden();
  await mkdir(artifacts, { recursive: true });
  await page.screenshot({ path: `${artifacts}/editor-custom-en.png` });
  reject = true;
  await width.fill("310");
  await apply.click();
  await expect(
    page.getByRole("button", { name: "Undo", exact: true }),
  ).toBeDisabled();
  const margin = page.getByLabel("Safe margin", { exact: true });
  await margin.fill("10");
  releaseFailure();
  await expect.poll(() => album.safe_margin_mm).toBe(10);
  await expect(width).toHaveValue("300.125");
  await expect(margin).toHaveValue("10");
  expect(album.page_width_mm).toBe(300.125);
  await width.fill("240");
  await expect(apply).toBeDisabled();
  const dimensions = AlbumMetaSchema.properties;
  const ratio = AlbumMetaSchema["x-page-aspect-ratio"];
  await expect(width).toHaveAttribute(
    "min",
    String(dimensions.page_width_mm.minimum),
  );
  await expect(height).toHaveAttribute(
    "max",
    String(dimensions.page_height_mm.maximum),
  );
  const range = page.locator('.page-size-settings [role="alert"]');
  await expect(range).toContainText(
    `${dimensions.page_width_mm.minimum}–${dimensions.page_width_mm.maximum} mm`,
  );
  await expect(range).toContainText(`${ratio.minimum}–${ratio.maximum}`);
  await page.getByRole("button", { name: "in", exact: true }).click();
  await expect(width).toHaveAttribute(
    "min",
    String(dimensions.page_width_mm.minimum / 25.4),
  );
  await expect(width).toHaveAttribute(
    "max",
    String(dimensions.page_width_mm.maximum / 25.4),
  );
  await expect(range).toContainText("in");
  await expect(apply).toBeDisabled();
  await page.screenshot({ path: `${artifacts}/editor-schema-bounds-en.png` });
  await page.getByRole("button", { name: "mm", exact: true }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.route("**/api/v1/users", (route) =>
    route.fulfill({ json: { ...mockUser, locale: "he-IL" } }),
  );
  await page.reload();
  await page.getByRole("button", { name: '"הדפסה" הרחב את' }).click();
  await page.locator(".context-panel .q-item").first().click();
  await expect(
    page.locator(".context-panel .q-expansion-item__content"),
  ).toBeHidden();
  await expect(page.locator(".page-size-settings")).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 768 });
  await expect
    .poll(() =>
      page
        .locator(".inspector-panel")
        .evaluate((el) => Math.round(el.getBoundingClientRect().width)),
    )
    .toBeLessThanOrEqual(240);
  await page.screenshot({ path: `${artifacts}/editor-custom-he.png` });
  await page.getByLabel("רוחב", { exact: true }).fill("240");
  await expect(range).toContainText(
    `רוחב ${dimensions.page_width_mm.minimum}–${dimensions.page_width_mm.maximum} mm`,
  );
  await expect(range).toContainText(`${ratio.minimum}–${ratio.maximum}`);
  await page.screenshot({ path: `${artifacts}/editor-schema-bounds-he.png` });
});

// Derive the language matrix from the actual application message inventory.
const localeDirectory = resolve(import.meta.dirname, "../src/i18n/locales");
for (const file of readdirSync(localeDirectory).filter((name) =>
  name.endsWith(".json"),
)) {
  const language = file.replace(".json", "");
  const messages = JSON.parse(
    readFileSync(resolve(localeDirectory, file), "utf8"),
  );
  test.describe(`page size locale ${language}`, () => {
    test.use({ locale: language });
    test("decimal entry, units and bounds fit the narrow inspector", async ({
      authedPage: page,
    }) => {
      const album = { ...mockAlbum, page_width_mm: 297, page_height_mm: 210 };
      await page.route("**/api/v1/users", (route) =>
        route.fulfill({ json: { ...mockUser, locale: language } }),
      );
      await page.route("**/api/v1/albums/aid-1", async (route) => {
        if (route.request().method() === "PATCH")
          Object.assign(album, route.request().postDataJSON());
        await route.fulfill({ json: album });
      });
      await page.setViewportSize({ width: 1024, height: 768 });
      await page.goto("/editor");
      await expect(page.locator("html")).toHaveAttribute("lang", language);
      const inspector = page.locator(".inspector-panel");
      if (language === "de") {
        await inspector.locator(".context-panel .q-item").first().click();
        await expect(
          inspector.locator(".context-panel .q-expansion-item__content"),
        ).toBeHidden();
        const properties = inspector
          .locator(".panel-section-header")
          .filter({ hasText: messages.editor.properties });
        await properties.click();
        const background = page.getByRole("button", {
          name: messages.editor.pageBackground,
          exact: true,
        });
        const reset = page.getByRole("button", {
          name: messages.editor.resetBackground,
          exact: true,
        });
        await expect(background).toBeVisible();
        await expect(reset).toBeDisabled();
        await background.click();
        const hex = page.locator(".q-color-picker__header input");
        await hex.fill("#ffeeaa");
        await hex.press("Tab");
        await expect.poll(() => album.background_color).toBe("#ffeeaa");
        await page.keyboard.press("Escape");
        await expect(page.locator(".q-color-picker")).toBeHidden();
        await expect
          .poll(() =>
            background.evaluate((el) => el.scrollWidth <= el.clientWidth),
          )
          .toBe(true);
        await expect
          .poll(() =>
            inspector
              .locator(".background-row")
              .evaluate((el) => el.scrollWidth <= el.clientWidth),
          )
          .toBe(true);
        await mkdir(artifacts, { recursive: true });
        await page.screenshot({
          path: `${artifacts}/editor-background-de.png`,
        });
        await reset.click();
        await expect.poll(() => album.background_color).toBe(null);
        await expect(reset).toBeDisabled();
        await properties.click();
      }
      await inspector
        .locator(".q-expansion-item")
        .filter({ hasText: messages.print.title })
        .first()
        .locator(".q-expansion-item__container > .q-item")
        .click();
      const settings = page.locator(".page-size-settings");
      await expect(settings).toBeVisible();
      await expect(settings).toContainText(messages.print.pageSize);
      await expect(settings).toContainText(messages.print.lockRatio);
      const width = settings.getByLabel(messages.print.pageWidth, {
        exact: true,
      });
      const height = settings.getByLabel(messages.print.pageHeight, {
        exact: true,
      });
      await settings.locator(".q-select").click();
      await expect(
        page.getByRole("option", { name: "US Letter", exact: true }),
      ).toBeVisible();
      await page.getByRole("option", { name: "US Legal", exact: true }).click();
      await expect(width).toHaveValue(
        new Intl.NumberFormat(language, { useGrouping: false }).format(355.6),
      );
      const fraction = new Intl.NumberFormat(language, {
        useGrouping: false,
      }).format(300.125);
      await width.fill("");
      await width.pressSequentially(fraction);
      await height.fill(
        new Intl.NumberFormat(language, { useGrouping: false }).format(220.25),
      );
      await settings.getByRole("button", { name: "in", exact: true }).click();
      await expect(width).toHaveValue(
        new Intl.NumberFormat(language, {
          useGrouping: false,
          maximumFractionDigits: 6,
        }).format(300.125 / 25.4),
      );
      await settings.getByRole("button", { name: "mm", exact: true }).click();
      await expect(width).toHaveValue(fraction);
      await settings
        .getByRole("button", { name: messages.print.applySize, exact: true })
        .click();
      await expect.poll(() => album.page_width_mm).toBe(300.125);
      await expect.poll(() => album.page_height_mm).toBe(220.25);
      await width.fill("240");
      const range = settings.locator('[role="alert"]');
      const ratio = AlbumMetaSchema["x-page-aspect-ratio"];
      const formatter = new Intl.NumberFormat(language, { useGrouping: false });
      await expect(range).toContainText(
        `${formatter.format(ratio.minimum)}–${formatter.format(ratio.maximum)}`,
      );
      await expect(
        settings.getByRole("button", {
          name: messages.print.applySize,
          exact: true,
        }),
      ).toBeDisabled();
      await expect(settings).toContainText(messages.print.customSize);
      await expect
        .poll(() => settings.evaluate((el) => el.scrollWidth <= el.clientWidth))
        .toBe(true);
      await mkdir(artifacts, { recursive: true });
      await page.screenshot({
        path: `${artifacts}/editor-locale-${language}.png`,
      });
    });
  });
}

test("PDF sheets use each trim size, bleed and physical cover spine with no blank sheets", async ({
  authedPage: page,
}) => {
  test.setTimeout(90_000);
  let size = { width: 297, height: 210, bleed: 0, cover: 0, spine: 0 };
  await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: {
          ...mockAlbum,
          page_width_mm: size.width,
          page_height_mm: size.height,
          interior_bleed_mm: size.bleed,
          cover_bleed_mm: size.cover,
          hidden_headers: ["overview", "full-map"],
          chapters: [{ ...mockAlbum.chapters[0], spine_width_mm: size.spine }],
          media: mockMedia,
        },
        steps: [
          {
            ...mockSteps[0],
            description: "Short narrative. סיפור בעברית.",
            weather: {
              day: { temp: 5, feels_like: 2, icon: "clear-day" },
              night: null,
            },
            pages: [],
            cover: null,
          },
        ],
        segments: [],
        total_distance_km: 0,
      },
    }),
  );
  await mkdir(artifacts, { recursive: true });
  for (const [label, width, height, bleed, cover, spine] of [
    ["a4", 297, 210, 0, 0, 0],
    ["letter", 279.4, 215.9, 3, 6, 12],
    ["legal", 355.6, 215.9, 0, 0, 0],
    ["min", 250, 180, 0, 0, 0],
    ["ratio-min", 250, 200, 3, 6, 12],
    ["ratio-max", 324, 180, 3, 6, 12],
    ["max", 420, 297, 20, 20, 100],
  ] as const) {
    size = { width, height, bleed, cover, spine };
    await page.emulateMedia({ media: "print" });
    await page.goto("/print/aid-1");
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
    const covers = await page
      .locator(".page-container")
      .evaluateAll((pages) =>
        pages.map((el) => el.classList.contains("cover-sheet")),
      );
    const count = covers.length;
    const pdf = await page.pdf({
      preferCSSPageSize: true,
      printBackground: true,
      path: `${artifacts}/${label}-combined.pdf`,
    });
    const boxes = Array.from(
      pdf.toString("latin1").matchAll(/\/MediaBox\s*\[([\d.\s-]+)\]/g),
      (match) => match[1].trim().split(/\s+/).map(Number),
    );
    expect(boxes).toHaveLength(count);
    for (const [index, box] of boxes.entries()) {
      const sheetBleed = covers[index] ? cover : bleed;
      expect((box[2] * 25.4) / 72).toBeCloseTo(width + 2 * sheetBleed, 0);
      expect((box[3] * 25.4) / 72).toBeCloseTo(height + 2 * sheetBleed, 0);
    }
    await page.goto("/print/aid-1?part=cover");
    await page.waitForFunction(
      () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
    );
    const coverPdf = await page.pdf({
      preferCSSPageSize: true,
      printBackground: true,
      path: `${artifacts}/${label}-cover.pdf`,
    });
    const coverBoxes = Array.from(
      coverPdf.toString("latin1").matchAll(/\/MediaBox\s*\[([\d.\s-]+)\]/g),
      (match) => match[1].trim().split(/\s+/).map(Number),
    );
    expect(coverBoxes).toHaveLength(1);
    expect((coverBoxes[0][2] * 25.4) / 72).toBeCloseTo(
      2 * width + spine + 2 * cover,
      0,
    );
    expect((coverBoxes[0][3] * 25.4) / 72).toBeCloseTo(height + 2 * cover, 0);
  }
});

test("export reports overflowing text slot IDs after a page resize without changing content", async ({
  authedPage: page,
}) => {
  const text = "A preserved long text tile. ".repeat(120);
  await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: {
          ...mockAlbum,
          page_width_mm: 250,
          page_height_mm: 180,
          hidden_headers: ["overview", "full-map"],
          media: mockMedia,
        },
        steps: [
          {
            ...mockSteps[0],
            description: "",
            pages: [
              {
                id: "composed-page",
                kind: "grid",
                media: [
                  "photo1.jpg",
                  "photo2.jpg",
                  "photo3.jpg",
                  "photo4.jpg",
                  "photo5.jpg",
                ],
                slots: [
                  {
                    id: "long-text",
                    kind: "text",
                    text,
                    frame_orientation: "portrait",
                  },
                  ...[
                    "photo1.jpg",
                    "photo2.jpg",
                    "photo3.jpg",
                    "photo4.jpg",
                    "photo5.jpg",
                  ].map((name, index) => ({
                    id: `photo-${index}`,
                    kind: "photo" as const,
                    media_name: name,
                  })),
                ],
              },
            ],
            cover: null,
          },
        ],
        segments: [],
        total_distance_km: 0,
      },
    }),
  );
  await page.goto("/print/aid-1");
  await page.waitForFunction(
    () => (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
  );
  const error = await page.evaluate(
    () => (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
  );
  expect(error).toMatchObject({
    code: "text-overflow",
    message: expect.stringContaining("long-text"),
  });
  await expect(page.locator('[data-text-slot="long-text"]')).toHaveText(
    text.trim(),
  );
  expect(
    await page.evaluate(
      () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
    ),
  ).not.toBe(true);
});

test("long English and Hebrew narratives reflow with size and font while preserving all text", async ({
  authedPage: page,
}) => {
  test.setTimeout(90_000);
  const description =
    "An English travel story with preserved details. סיפור מסע בעברית עם פרטים שמורים. "
      .repeat(120)
      .trim();
  let dimensions = {
    page_width_mm: 250,
    page_height_mm: 180,
    body_font: "Frank Ruhl Libre",
  };
  await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: {
          ...mockAlbum,
          ...dimensions,
          hidden_headers: ["overview", "full-map"],
          media: mockMedia,
        },
        steps: [
          {
            ...mockSteps[0],
            description,
            pages: [],
            cover: null,
            weather: null,
          },
        ],
        segments: [],
        total_distance_km: 0,
      },
    }),
  );
  const counts: number[] = [];
  for (const geometry of [
    dimensions,
    {
      page_width_mm: 355.6,
      page_height_mm: 215.9,
      body_font: "Frank Ruhl Libre",
    },
    { page_width_mm: 355.6, page_height_mm: 215.9, body_font: "Assistant" },
  ]) {
    dimensions = geometry;
    await page.goto("/print/aid-1");
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
    const fragments = await page
      .locator(".description, .description-text")
      .allTextContents();
    expect(fragments.join("").replace(/\s+/g, " ").trim()).toBe(description);
    counts.push(fragments.length);
  }
  expect(counts[0]).toBeGreaterThan(counts[1]);
});
