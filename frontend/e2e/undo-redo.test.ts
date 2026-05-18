import {
  expect,
  openEditor,
  photoButtons,
  scrollToStep,
  test,
} from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

/** The unused photo count badge in the inspector panel. */
function unusedBadge(page: Page): Locator {
  return page
    .getByRole("complementary")
    .filter({ hasText: "Unused" })
    .getByText(/^\d+$/);
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

    await photoButtons(page).first().click();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });

    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("0", { timeout: 3_000 });
  });

  test("Ctrl+Z after sendToUnused restores focus to the moved photo", async ({
    focusPage: page,
  }) => {
    const photo = photoButtons(page).first();
    await photo.click();
    const originalMedia = await photo.getAttribute("data-media");

    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(unusedBadge(page)).toHaveText("1", { timeout: 3_000 });

    await page.keyboard.press("Control+z");
    await expect(unusedBadge(page)).toHaveText("0", { timeout: 3_000 });

    await expect(
      page.locator(`[data-media="${originalMedia}"]`),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("Ctrl+Shift+Z re-applies the undone action", async ({
    focusPage: page,
  }) => {
    await expect(unusedBadge(page)).toHaveText("0");

    await photoButtons(page).first().click();
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
    await photoButtons(page).first().click();
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
