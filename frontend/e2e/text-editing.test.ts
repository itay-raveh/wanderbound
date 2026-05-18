import { expect, openEditor, scrollToStep, test } from "./fixtures";
import type { Page, Locator } from "@playwright/test";

/** Find the first step name textbox (aria-label="Step name") in the viewer. */
function stepNameTextbox(page: Page): Locator {
  return page
    .getByRole("main")
    .getByRole("textbox", { name: "Step name" })
    .first();
}

async function editStepName(page: Page, value: string, commitKey: string) {
  const textbox = stepNameTextbox(page);
  await expect(textbox).toContainText("Buenos Aires");
  await textbox.click();
  await page.keyboard.press("Control+a");
  await page.keyboard.type(value);
  await page.keyboard.press(commitKey);
  return textbox;
}

test.describe("Text editing", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
    await scrollToStep(page, "Argentina", "Buenos Aires");
  });

  test("editing step name persists on blur", async ({ focusPage: page }) => {
    const textbox = await editStepName(page, "Renamed", "Enter");

    // text-transform: uppercase means typed text is stored uppercase in the DOM
    await expect(textbox).toContainText("RENAMED", { timeout: 3_000 });
  });

  test("Escape reverts edit without saving", async ({ focusPage: page }) => {
    const textbox = await editStepName(page, "Discarded", "Escape");

    // Escape restores modelValue via textContent assignment - original case preserved
    await expect(textbox).toContainText("Buenos Aires", { timeout: 3_000 });
  });

  test("Ctrl+Z after editing step name restores original", async ({
    focusPage: page,
  }) => {
    const textbox = await editStepName(page, "Renamed", "Enter");
    await expect(textbox).toContainText("RENAMED", { timeout: 3_000 });

    // Undo - focus is off the contenteditable, so Ctrl+Z hits the undo stack
    await page.keyboard.press("Control+z");

    // Vue re-renders with original modelValue - original case restored
    await expect(textbox).toContainText("Buenos Aires", { timeout: 5_000 });
  });
});
