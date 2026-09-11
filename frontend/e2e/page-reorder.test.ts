import { expect, openEditor, test } from "./fixtures";
import {
  mockAlbum,
  mockAuthStateAuthenticated,
  mockMedia,
  mockStep,
  mockUser,
} from "../tests/fixtures/mocks";
import type { StepMediaLayout } from "../src/client";

for (const rtl of [false, true]) {
  test(`reorders whole photo pages, persists them, and supports undo (${rtl ? "RTL" : "LTR"})`, async ({
    authedPage: page,
  }) => {
    await page.setViewportSize({ width: rtl ? 1024 : 1600, height: 1000 });
    await page.emulateMedia({
      reducedMotion: "reduce",
      colorScheme: rtl ? "dark" : "light",
    });
    const user = { ...mockUser, locale: rtl ? "he" : "en-US" };
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ json: user }),
    );
    await page.route("**/api/v1/auth/state", (route) =>
      route.fulfill({ json: { ...mockAuthStateAuthenticated, user } }),
    );
    const original: StepMediaLayout = {
      cover: "cover.jpg",
      pages: [
        { kind: "grid", media: ["a.jpg", "b.jpg"] },
        { kind: "panorama_spread", media: ["wide.jpg"] },
        { kind: "grid", media: ["c.jpg"] },
      ],
      unused: ["unused.jpg"],
    };
    let step = { ...mockStep, ...original, aid: "aid-1", uid: 1 };
    const other = {
      ...mockStep,
      id: 2,
      aid: "aid-1",
      uid: 1,
      name: "Rotterdam",
    };
    const updates: StepMediaLayout[] = [];
    await page.route("**/api/v1/albums/aid-1", (route) =>
      route.fulfill({
        json: {
          ...mockAlbum,
          chapters: [{ ...mockAlbum.chapters[0], step_ids: [1, 2] }],
        },
      }),
    );
    await page.route("**/api/v1/albums/aid-1/steps", (route) =>
      route.fulfill({ json: [step, other] }),
    );
    await page.route("**/api/v1/albums/aid-1/media", (route) =>
      route.fulfill({
        json: [
          ...mockMedia,
          ...["a.jpg", "b.jpg", "wide.jpg", "c.jpg", "unused.jpg"].map(
            (name) => ({ name, width: 1920, height: 1080 }),
          ),
        ],
      }),
    );
    await page.route(
      "**/api/v1/albums/aid-1/steps/1/media-layout",
      async (route) => {
        const layout: StepMediaLayout = route.request().postDataJSON();
        updates.push(layout);
        step = { ...step, ...layout };
        await route.fulfill({ json: step });
      },
    );
    await openEditor(page);
    await page.locator('[data-nav-step="1"]').click();
    const rows = page.locator(".step-photo-pages .page-row");
    await expect(rows).toHaveCount(3);
    const first = rows.nth(0).locator(".page-drag-handle");
    await first.dragTo(rows.nth(2), { targetPosition: { x: 40, y: 50 } });
    await expect
      .poll(() => step.pages)
      .toEqual([original.pages[1], original.pages[2], original.pages[0]]);
    expect(updates[0]).toEqual({
      ...original,
      pages: [original.pages[1], original.pages[2], original.pages[0]],
    });
    await page.keyboard.press("Control+z");
    await expect.poll(() => step.pages).toEqual(original.pages);
    await rows
      .nth(2)
      .getByRole("button", {
        name: rtl ? "שינוי מיקום עמוד תמונות 3" : "Reorder photo page 3",
      })
      .click();
    await page
      .getByRole("menuitem", { name: rtl ? "הזזה למעלה" : "Move up" })
      .click();
    await expect
      .poll(() => step.pages)
      .toEqual([original.pages[0], original.pages[2], original.pages[1]]);
    await page.reload();
    await expect
      .poll(() => step.pages)
      .toEqual([original.pages[0], original.pages[2], original.pages[1]]);
    await page.locator('[data-nav-step="1"]').click();
    await expect(rows.nth(2)).toHaveAttribute(
      "data-page-key",
      JSON.stringify(["wide.jpg"]),
    );
    expect(step.cover).toBe(original.cover);
    expect(step.unused).toEqual(original.unused);
    expect(other.pages).toEqual(mockStep.pages);
  });
}
