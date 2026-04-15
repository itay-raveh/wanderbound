import { test, expect } from "./fixtures";
import type { Page, Locator } from "@playwright/test";

function photos(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed]');
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

/** Find the first step name textbox (aria-label="Step name") in the viewer. */
function stepNameTextbox(page: Page): Locator {
  return page.getByRole("main").getByRole("textbox", { name: "Step name" }).first();
}

test.describe("Text editing", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
    await scrollToStep(page, "Argentina", "Buenos Aires");
  });

  test("editing step name persists on blur", async ({ focusPage: page }) => {
    const textbox = stepNameTextbox(page);
    await expect(textbox).toContainText("Buenos Aires");

    await textbox.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Renamed");

    // Enter blurs single-line contenteditable (EditableText.vue onKeydown)
    await page.keyboard.press("Enter");

    // text-transform: uppercase means typed text is stored uppercase in the DOM
    await expect(textbox).toContainText("RENAMED", { timeout: 3_000 });
  });

  test("Escape reverts edit without saving", async ({ focusPage: page }) => {
    const textbox = stepNameTextbox(page);
    await expect(textbox).toContainText("Buenos Aires");

    await textbox.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Discarded");
    await page.keyboard.press("Escape");

    // Escape restores modelValue via textContent assignment - original case preserved
    await expect(textbox).toContainText("Buenos Aires", { timeout: 3_000 });
  });

  test("Ctrl+Z after editing step name restores original", async ({
    focusPage: page,
  }) => {
    const textbox = stepNameTextbox(page);
    await expect(textbox).toContainText("Buenos Aires");

    // Edit and commit via blur
    await textbox.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Renamed");
    await page.keyboard.press("Enter");
    await expect(textbox).toContainText("RENAMED", { timeout: 3_000 });

    // Undo - focus is off the contenteditable, so Ctrl+Z hits the undo stack
    await page.keyboard.press("Control+z");

    // Vue re-renders with original modelValue - original case restored
    await expect(textbox).toContainText("Buenos Aires", { timeout: 5_000 });
  });
});
