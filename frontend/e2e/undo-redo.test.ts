import { test, expect } from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

function photos(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed]');
}

/** The unused photo count badge in the inspector panel. */
function unusedBadge(page: Page): Locator {
  return page
    .getByRole("complementary")
    .filter({ hasText: "Unused" })
    .getByText(/^\d+$/);
}

async function openEditor(page: Page) {
  await page.goto("/editor");
  await expect(page.getByText("South America")).toBeVisible({
    timeout: 15_000,
  });
}

async function scrollToStep(page: Page, country: string, stepName: string) {
  const nav = page.getByRole("navigation");
  await nav.getByText(country).click();
  const step = nav.getByText(stepName);
  await expect(step).toBeVisible({ timeout: 3_000 });
  await step.click();
  await expect(photos(page).first()).toBeVisible({ timeout: 5_000 });
}

test.describe("Undo & redo", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
    await scrollToStep(page, "Argentina", "Buenos Aires");
  });

  test("Ctrl+Z after sendToUnused restores the photo", async ({
    focusPage: page,
  }) => {
    await expect(unusedBadge(page)).toHaveText("0");

    await photos(page).first().click();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });

    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("0", { timeout: 3_000 });
  });

  test("Ctrl+Shift+Z re-applies the undone action", async ({
    focusPage: page,
  }) => {
    await expect(unusedBadge(page)).toHaveText("0");

    await photos(page).first().click();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });

    // Undo
    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("0", { timeout: 3_000 });

    // Redo
    await page.keyboard.press("Control+Shift+z");
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });
  });

  test("multiple sequential undos restore multiple actions", async ({
    focusPage: page,
  }) => {
    await expect(unusedBadge(page)).toHaveText("0");

    // Send two photos to unused
    await photos(page).first().click();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("2", { timeout: 3_000 });

    // Undo both
    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });
    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("0", { timeout: 3_000 });
  });
});
