import {
  expect,
  openEditor,
  photoButtons,
  scrollToStep,
  test,
} from "./fixtures";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

test.describe("Undo & redo", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
    await scrollToStep(page, "Buenos Aires");
  });

  test("keyboard undo and redo preserve the moved photo and restore focus", async ({
    focusPage: page,
  }) => {
    const first = photoButtons(page).first();
    const name = await first.getAttribute("data-media");
    const onPage = page.locator(`.page-content [data-media="${name}"]`);
    const unused = page.locator(`.unused-drawer [data-media="${name}"]`);
    await first.click();
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(onPage).toHaveCount(0);
    await expect(unused).toBeVisible();

    await page.keyboard.press("Control+z");
    await expect(onPage).toBeVisible();
    await expect(onPage).toHaveAttribute("aria-pressed", "true");
    await expect(onPage).toBeFocused();
    await expect(unused).toHaveCount(0);

    await page.keyboard.press("Control+Shift+z");
    await expect(onPage).toHaveCount(0);
    await expect(unused).toBeVisible();
  });
});
