import { test, expect } from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

// ---------------------------------------------------------------------------
// Helpers — purely user-facing selectors
// ---------------------------------------------------------------------------

/** All focusable photos (role="button" with aria-pressed). */
function photos(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed]');
}

/** The currently selected photo (exactly 0 or 1 expected). */
function selected(page: Page): Locator {
  return page.locator('[aria-pressed="true"]');
}

/** Navigate to the editor and wait for it to load. */
async function openEditor(page: Page) {
  await page.goto("/editor");
  await expect(page.getByText("South America")).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Navigate to a step by clicking its country group, then its name
 * in the sidebar — the same way a real user would.
 */
async function scrollToStep(page: Page, country: string, stepName: string) {
  const nav = page.getByRole("navigation");
  // Expand the country group (click the country name header).
  await nav.getByText(country).click();
  // Wait for the step name to become visible inside the expanded group.
  const step = nav.getByText(stepName);
  await expect(step).toBeVisible({ timeout: 3_000 });
  // Click the step to scroll the album viewer there.
  await step.click();
  // Wait for the virtualizer to scroll and mount the step's pages.
  await expect(photos(page).first()).toBeVisible({ timeout: 5_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Photo focus & arrow navigation", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
  });

  test("click selects a photo", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    const photo = photos(page).first();
    await photo.click();

    await expect(selected(page)).toHaveCount(1);
    await expect(photo).toHaveAttribute("aria-pressed", "true");
  });

  test("Escape deselects", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();
    await expect(selected(page)).toHaveCount(1);

    await page.keyboard.press("Escape");
    await expect(selected(page)).toHaveCount(0);
  });

  test("ArrowRight moves selection to next photo", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    const first = photos(page).first();
    await first.click();
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowRight");

    // The first photo should no longer be selected.
    await expect(first).toHaveAttribute("aria-pressed", "false");
    // Exactly one photo should be selected — a different one.
    await expect(selected(page)).toHaveCount(1);
  });

  test("ArrowLeft moves selection to previous photo", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");

    // Select the second visible photo.
    const second = photos(page).nth(1);
    await second.click();
    await expect(second).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowLeft");

    await expect(second).toHaveAttribute("aria-pressed", "false");
    await expect(selected(page)).toHaveCount(1);
  });

  test("ArrowRight crosses step boundary", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();
    await expect(selected(page)).toHaveCount(1);

    // Arrow to the last photo of the first step (3 navigable photos → 2 presses).
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    const beforeBoundary = await selected(page).boundingBox();

    // One more press crosses into the next step.
    await page.keyboard.press("ArrowRight");

    // Selection should still be valid, visible, and at a different position.
    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
    const afterBoundary = await selected(page).boundingBox();
    expect(afterBoundary!.y).not.toBeCloseTo(beforeBoundary!.y, -1);
  });

  test("ArrowLeft crosses step boundary", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();

    // Arrow 3 times to cross into step 2 (first photo of step 2).
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press("ArrowRight");
    }
    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    const inStep2 = await selected(page).boundingBox();

    // Press ArrowLeft to go back across the boundary.
    await page.keyboard.press("ArrowLeft");

    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
    const backInStep1 = await selected(page).boundingBox();
    expect(backInStep1!.y).not.toBeCloseTo(inStep2!.y, -1);
  });

  test("arrow navigation continues after crossing a step boundary", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();

    // Cross into step 2 (3 arrows) then continue forward (2 more).
    // If the step boundary broke internal state, the 4th+ arrows
    // would snap back to the previous step instead of continuing.

    // Track which DOM element is selected at each step using its index
    // among all [aria-pressed] elements in the document.
    async function selectedIndex(): Promise<number> {
      return selected(page).evaluate((el) => {
        const all = [...document.querySelectorAll("[aria-pressed]")];
        return all.indexOf(el);
      });
    }

    const indices: number[] = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("ArrowRight");
      await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
      indices.push(await selectedIndex());
    }

    // Every arrow press should land on a different photo — no revisits.
    const unique = new Set(indices);
    expect(unique.size).toBe(indices.length);
  });

  test("forward then backward is a round trip", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();

    async function selectedIndex(): Promise<number> {
      return selected(page).evaluate((el) => {
        const all = [...document.querySelectorAll("[aria-pressed]")];
        return all.indexOf(el);
      });
    }

    const startIdx = await selectedIndex();

    // Go forward 4 times (crosses into step 2).
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press("ArrowRight");
      await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    }

    // Go backward 4 times (should return to start).
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press("ArrowLeft");
      await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    }

    const endIdx = await selectedIndex();
    expect(endIdx).toBe(startIdx);
  });

  test("rapid ArrowRight presses settle with one selected photo", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();
    await expect(selected(page)).toHaveCount(1);

    // Fire several rapid arrow presses — enough to cross at least one step boundary.
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("ArrowRight");
    }

    // After settling, exactly one photo should be selected and visible.
    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Send-to-unused & set-as-cover shortcuts
// ---------------------------------------------------------------------------

test.describe("Send to unused & set as cover", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
  });

  test("sendToUnused removes photo and advances focus", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();
    await expect(selected(page)).toHaveCount(1);

    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);

    // Focus should advance to a remaining photo (not drop).
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await expect(selected(page)).toBeInViewport();
  });

  test("sendToUnused on last navigable photo advances to previous", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");

    // Navigate to the last navigable photo (3 navigable → 2 ArrowRight presses).
    await photos(page).first().click();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await expect(selected(page)).toHaveCount(1);

    // Track which DOM element is selected by its index among all focusable photos.
    async function selectedIndex(): Promise<number> {
      return selected(page).evaluate((el) => {
        const all = [...document.querySelectorAll("[aria-pressed]")];
        return all.indexOf(el);
      });
    }

    const indexBefore = await selectedIndex();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);

    // Focus should move backward — the selected index should decrease.
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    const indexAfter = await selectedIndex();
    expect(indexAfter).toBeLessThan(indexBefore);
  });

  test("sendToUnused on the only remaining photo clears focus", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    await photos(page).first().click();

    // Remove the first two navigable photos, leaving only one.
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });

    // Now only one navigable photo remains — removing it should clear focus.
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(0, { timeout: 3_000 });
  });

  test("setAsCover advances focus to next photo", async ({ focusPage: page }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    const first = photos(page).first();
    await first.click();
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press(PHOTO_SHORTCUTS.setAsCover);

    // Focus should advance — the photo became cover, so it's no longer navigable.
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await expect(first).not.toHaveAttribute("aria-pressed", "true");
  });
});
