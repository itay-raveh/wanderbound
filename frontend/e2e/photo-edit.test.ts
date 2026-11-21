import { expect, openEditor, scrollToStep, test } from "./fixtures";
import en from "../src/i18n/locales/en.json" with { type: "json" };
import he from "../src/i18n/locales/he.json" with { type: "json" };
import {
  mockAuthStateAuthenticated,
  mockMedia,
  mockStep,
} from "../tests/fixtures/mocks";

const source = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100" viewBox="0 0 160 100"><rect width="160" height="100" fill="#2972aa"/><circle cx="100" cy="50" r="25" fill="#ffce54"/></svg>`;

for (const [locale, labels] of [
  ["en-US", en],
  ["he-IL", he],
] as const) {
  test(`edits visible photo pixels with physical crop controls in ${locale}`, async ({
    authedPage: page,
  }, testInfo) => {
    await page.route("**/api/v1/auth/state", (route) =>
      route.fulfill({
        json: {
          ...mockAuthStateAuthenticated,
          user: { ...mockAuthStateAuthenticated.user, locale },
        },
      }),
    );
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ json: { ...mockAuthStateAuthenticated.user, locale } }),
    );
    let savedEdit: Record<string, number> | null = null;
    let media = mockMedia.map((item) => ({
      ...item,
      aid: "aid-1",
      uid: 1,
      kind: "photo",
      panorama_candidate: false,
      photo_edit: null as Record<string, number> | null,
      updated_at: "2026-09-29T00:00:00Z",
    }));
    await page.route("**/api/v1/albums/aid-1/media", (route) =>
      route.fulfill({ json: media }),
    );
    await page.route("**/api/v1/albums/aid-1/steps", (route) =>
      route.fulfill({ json: [{ ...mockStep, unused: ["photo2.jpg"] }] }),
    );
    await page.route("**/api/v1/albums/aid-1/media/*.jpg*", (route) =>
      route.fulfill({ contentType: "image/svg+xml", body: source }),
    );
    await page.route(
      "**/api/v1/albums/aid-1/media/photo1.jpg/photo-source*",
      (route) => route.fulfill({ contentType: "image/svg+xml", body: source }),
    );
    await page.route(
      "**/api/v1/albums/aid-1/media/photo1.jpg/photo-edit",
      (route) => {
        savedEdit = route.request().postDataJSON() as Record<string, number>;
        media = media.map((item) =>
          item.name === "photo1.jpg"
            ? {
                ...item,
                photo_edit: savedEdit,
                updated_at: "2026-09-29T00:01:00Z",
              }
            : item,
        );
        return route.fulfill({
          json: media.find((item) => item.name === "photo1.jpg"),
        });
      },
    );
    await openEditor(page);
    await scrollToStep(page, "Amsterdam");
    await page
      .locator('[data-media="photo1.jpg"] .album-action')
      .first()
      .click();
    const dialog = page.getByRole("dialog", { name: labels.photoEdit.title });
    await expect(dialog).toBeVisible();
    const range = dialog.getByRole("slider", {
      name: labels.photoEdit.rotation,
    });
    await expect(range).toHaveAttribute("min", "-180");
    await expect(range).toHaveAttribute("max", "180");
    await expect(dialog.locator(".crop-box")).toBeVisible();

    await dialog
      .getByRole("spinbutton", { name: labels.photoEdit.angleExact })
      .click();
    const canvas = dialog.locator(".photo-edit-canvas");
    const image = dialog.locator(".source-image");
    await expect(image).toBeVisible();
    const bounds = await canvas.boundingBox();
    const imageBounds = await image.boundingBox();
    expect(imageBounds!.x).toBeCloseTo(bounds!.x, 0);
    expect(imageBounds!.y).toBeCloseTo(bounds!.y, 0);
    expect(imageBounds!.width).toBeCloseTo(bounds!.width, 0);
    // Inspect the rendered pixels, not merely a loaded image hidden off-canvas.
    const rendered = await canvas.screenshot({
      path: testInfo.outputPath("crop-visible.png"),
    });
    await testInfo.attach(`crop-visible-${locale}`, {
      body: rendered,
      contentType: "image/png",
    });
    const pixels = await page.evaluate(
      async (bytes) => {
        const bitmap = await createImageBitmap(
          new Blob([new Uint8Array(bytes)], { type: "image/png" }),
        );
        const canvas = document.createElement("canvas");
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext("2d")!;
        context.drawImage(bitmap, 0, 0);
        const pixel = (x: number, y: number) =>
          [
            ...context.getImageData(
              Math.floor(x * canvas.width),
              Math.floor(y * canvas.height),
              1,
              1,
            ).data,
          ].slice(0, 3);
        return { background: pixel(0.2, 0.2), subject: pixel(0.625, 0.5) };
      },
      [...rendered],
    );
    expect(pixels.background).toEqual([41, 114, 170]);
    expect(pixels.subject).toEqual([255, 206, 84]);
    expect(
      await dialog
        .locator(".preview-controls")
        .evaluate((el) => getComputedStyle(el).direction),
    ).toBe(locale === "he-IL" ? "rtl" : "ltr");

    await dialog.getByRole("slider", { name: labels.photoEdit.zoom }).fill("2");
    for (const corner of ["nw", "ne", "sw", "se"]) {
      const crop = dialog.locator(".crop-box");
      const before = (await crop.boundingBox())!;
      const handle = (await dialog
        .locator(`.crop-handle.${corner}`)
        .boundingBox())!;
      const west = corner.endsWith("w");
      const north = corner.startsWith("n");
      const x = handle.x + handle.width / 2;
      const y = handle.y + handle.height / 2;
      expect(
        Math.abs(x - (west ? before.x : before.x + before.width)),
      ).toBeLessThanOrEqual(2.1);
      expect(
        Math.abs(y - (north ? before.y : before.y + before.height)),
      ).toBeLessThanOrEqual(2.1);
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x + (west ? 12 : -12), y + (north ? 10 : -10), {
        steps: 4,
      });
      await page.mouse.up();
      const after = (await crop.boundingBox())!;
      expect(after.width).toBeLessThan(before.width - 8);
      expect(after.height).toBeLessThan(before.height - 6);
      expect(west ? after.x + after.width : after.x).toBeCloseTo(
        west ? before.x + before.width : before.x,
        0,
      );
      expect(north ? after.y + after.height : after.y).toBeCloseTo(
        north ? before.y + before.height : before.y,
        0,
      );
    }

    const angle = dialog.getByRole("spinbutton", {
      name: labels.photoEdit.angleExact,
    });
    // fill() does not wait for stability; finish opening before editing the draft.
    await angle.click();
    await angle.fill("90");
    await dialog
      .getByRole("spinbutton", { name: labels.photoEdit.angleExact })
      .blur();
    await expect(
      dialog.getByRole("spinbutton", { name: labels.photoEdit.angleExact }),
    ).toHaveValue("90.0");
    const rotatedCanvas = (await canvas.boundingBox())!;
    const rotatedImage = (await image.boundingBox())!;
    for (const key of ["x", "y", "width", "height"] as const)
      expect(rotatedImage[key]).toBeCloseTo(rotatedCanvas[key], 0);
    await dialog.getByRole("slider", { name: labels.photoEdit.zoom }).fill("2");
    const crop = dialog.locator(".crop-box");
    const before = await crop.evaluate((element) => element.style.left);
    await crop.focus();
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(() => crop.evaluate((element) => element.style.left))
      .not.toBe(before);
    await dialog.getByRole("button", { name: labels.photoEdit.apply }).click();
    await expect(dialog).toBeHidden();
    expect(savedEdit?.angle).toBe(90);

    await page.reload();
    await openEditor(page);
    await scrollToStep(page, "Amsterdam");
    await page
      .locator('[data-media="photo1.jpg"] .album-action')
      .first()
      .click();
    await expect(
      dialog.getByRole("spinbutton", { name: labels.photoEdit.angleExact }),
    ).toHaveValue("90.0");
    const persisted = await crop.evaluate((el) => ({
      x: parseFloat(el.style.left) / 100,
      y: parseFloat(el.style.top) / 100,
      width: parseFloat(el.style.width) / 100,
      height: parseFloat(el.style.height) / 100,
    }));
    for (const key of ["x", "y", "width", "height"] as const)
      expect(persisted[key]).toBeCloseTo(savedEdit![key], 4);
    await dialog.locator(".cancel-button").click();
    if (locale === "he-IL") return;
    await expect(
      page.locator(
        '.unused-drawer [data-media="photo2.jpg"] button[aria-label="Edit photo"]',
      ),
    ).toHaveCount(0);

    await page
      .getByRole("button", { name: "Print preview", exact: true })
      .click();
    const preview = page.getByRole("dialog", { name: "Print preview" });
    await preview.getByRole("button", { name: "Next spread" }).click();
    await preview.getByRole("button", { name: "Next spread" }).click();
    await expect(preview.locator('img[src*="photo1.jpg"]')).toHaveCount(1);
    await expect(
      preview.getByRole("button", { name: labels.photoEdit.title }),
    ).toHaveCount(0);
  });
}
