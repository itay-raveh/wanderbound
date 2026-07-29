import {
  expect,
  openEditor,
  photoButtons,
  scrollToStep,
  test,
} from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

function photos(page: Page): Locator {
  return photoButtons(page);
}

function selected(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed="true"]');
}

async function expectOneSelected(page: Page, timeout = 3_000) {
  await expect(selected(page)).toHaveCount(1, { timeout });
}

async function selectFirstPhoto(page: Page): Promise<Locator> {
  await scrollToStep(page, "Buenos Aires");
  const first = photos(page).first();
  await first.click();
  await expectOneSelected(page);
  return first;
}

async function press(page: Page, key: string, times: number) {
  for (let i = 0; i < times; i++) {
    await page.keyboard.press(key);
    await expectOneSelected(page);
  }
}

test.describe("Photo focus & arrow navigation", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
  });

  test("ArrowRight moves DOM focus to the selected photo", async ({
    focusPage: page,
  }) => {
    const first = await selectFirstPhoto(page);
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowRight");
    await expectOneSelected(page);

    await expect
      .poll(async () =>
        selected(page).evaluate(
          (el) =>
            document.activeElement?.getAttribute("data-media") ===
            el.getAttribute("data-media"),
        ),
      )
      .toBe(true);
  });

  test("ArrowRight crosses step boundary", async ({ focusPage: page }) => {
    await selectFirstPhoto(page);

    await press(page, "ArrowRight", 2);
    const beforeBoundary = await selected(page).boundingBox();

    await page.keyboard.press("ArrowRight");

    await expectOneSelected(page, 5_000);
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
    const afterBoundary = await selected(page).boundingBox();
    expect(afterBoundary!.y).not.toBeCloseTo(beforeBoundary!.y, -1);
  });
});

test.describe("Send to unused & set as cover", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
  });

  test("sendToUnused removes photo and advances focus", async ({
    focusPage: page,
  }) => {
    await selectFirstPhoto(page);

    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);

    await expectOneSelected(page);
    await expect(selected(page)).toBeInViewport();
  });

  test("setAsCover advances focus to next photo", async ({
    focusPage: page,
  }) => {
    const first = await selectFirstPhoto(page);
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press(PHOTO_SHORTCUTS.setAsCover);

    await expectOneSelected(page);
    await expect(first).not.toHaveAttribute("aria-pressed", "true");
  });
});
