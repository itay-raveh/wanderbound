import { test, expect } from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { PHOTO_SHORTCUTS } from "../src/composables/shortcutKeys";

function photos(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed]');
}

function selected(page: Page): Locator {
  return page.locator('[role="button"][aria-pressed="true"]');
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

async function selectFirstPhoto(page: Page): Promise<Locator> {
  await scrollToStep(page, "Argentina", "Buenos Aires");
  const first = photos(page).first();
  await first.click();
  await expect(selected(page)).toHaveCount(1);
  return first;
}

async function selectedIndex(page: Page): Promise<number> {
  return selected(page).evaluate((el) => {
    const all = [...document.querySelectorAll('[role="button"][aria-pressed]')];
    return all.indexOf(el);
  });
}

async function press(page: Page, key: string, times: number) {
  for (let i = 0; i < times; i++) {
    await page.keyboard.press(key);
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
  }
}

test.describe("Photo focus & arrow navigation", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await openEditor(page);
  });

  test("click selects a photo", async ({ focusPage: page }) => {
    const photo = await selectFirstPhoto(page);

    await expect(photo).toHaveAttribute("aria-pressed", "true");
  });

  test("Escape deselects", async ({ focusPage: page }) => {
    await selectFirstPhoto(page);

    await page.keyboard.press("Escape");
    await expect(selected(page)).toHaveCount(0);
  });

  test("ArrowRight moves selection to next photo", async ({
    focusPage: page,
  }) => {
    const first = await selectFirstPhoto(page);
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowRight");

    await expect(first).toHaveAttribute("aria-pressed", "false");
    await expect(selected(page)).toHaveCount(1);
  });

  test("ArrowRight moves DOM focus to the selected photo", async ({
    focusPage: page,
  }) => {
    const first = await selectFirstPhoto(page);
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowRight");
    await expect(selected(page)).toHaveCount(1);

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

  test("ArrowLeft moves selection to previous photo", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");

    const second = photos(page).nth(1);
    await second.click();
    await expect(second).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowLeft");

    await expect(second).toHaveAttribute("aria-pressed", "false");
    await expect(selected(page)).toHaveCount(1);
  });

  test("ArrowRight crosses step boundary", async ({ focusPage: page }) => {
    await selectFirstPhoto(page);

    await press(page, "ArrowRight", 2);
    const beforeBoundary = await selected(page).boundingBox();

    await page.keyboard.press("ArrowRight");

    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
    const afterBoundary = await selected(page).boundingBox();
    expect(afterBoundary!.y).not.toBeCloseTo(beforeBoundary!.y, -1);
  });

  test("ArrowLeft crosses step boundary", async ({ focusPage: page }) => {
    await selectFirstPhoto(page);

    await press(page, "ArrowRight", 3);
    const inStep2 = await selected(page).boundingBox();

    await page.keyboard.press("ArrowLeft");

    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
    const backInStep1 = await selected(page).boundingBox();
    expect(backInStep1!.y).not.toBeCloseTo(inStep2!.y, -1);
  });

  test("arrow navigation continues after crossing a step boundary", async ({
    focusPage: page,
  }) => {
    await selectFirstPhoto(page);

    const indices: number[] = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("ArrowRight");
      await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
      indices.push(await selectedIndex(page));
    }

    const unique = new Set(indices);
    expect(unique.size).toBe(indices.length);
  });

  test("forward then backward is a round trip", async ({ focusPage: page }) => {
    await selectFirstPhoto(page);

    const startIdx = await selectedIndex(page);

    await press(page, "ArrowRight", 4);
    await press(page, "ArrowLeft", 4);

    const endIdx = await selectedIndex(page);
    expect(endIdx).toBe(startIdx);
  });

  test("rapid ArrowRight presses settle with one selected photo", async ({
    focusPage: page,
  }) => {
    await selectFirstPhoto(page);

    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("ArrowRight");
    }

    await expect(selected(page)).toHaveCount(1, { timeout: 5_000 });
    await expect(selected(page)).toBeInViewport({ timeout: 5_000 });
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

    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await expect(selected(page)).toBeInViewport();
  });

  test("sendToUnused on last navigable photo advances to previous", async ({
    focusPage: page,
  }) => {
    await selectFirstPhoto(page);
    await press(page, "ArrowRight", 2);

    const indexBefore = await selectedIndex(page);
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);

    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    const indexAfter = await selectedIndex(page);
    expect(indexAfter).toBeLessThan(indexBefore);
  });

  test("sendToUnused on the only remaining photo clears focus", async ({
    focusPage: page,
  }) => {
    await selectFirstPhoto(page);

    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });

    await page.keyboard.press(PHOTO_SHORTCUTS.sendToUnused);
    await expect(selected(page)).toHaveCount(0, { timeout: 3_000 });
  });

  test("setAsCover advances focus to next photo", async ({
    focusPage: page,
  }) => {
    const first = await selectFirstPhoto(page);
    await expect(first).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press(PHOTO_SHORTCUTS.setAsCover);

    await expect(selected(page)).toHaveCount(1, { timeout: 3_000 });
    await expect(first).not.toHaveAttribute("aria-pressed", "true");
  });

  test("empty unused tray keeps a usable drop target", async ({
    focusPage: page,
  }) => {
    await scrollToStep(page, "Argentina", "Buenos Aires");
    const track = page.locator(".unused-drawer .drawer-track");

    await expect
      .poll(async () => {
        const box = await track.boundingBox();
        return box?.height ?? 0;
      })
      .toBeGreaterThan(40);
  });
});
