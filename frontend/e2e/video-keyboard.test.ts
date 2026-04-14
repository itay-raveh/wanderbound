import { test, expect } from "./fixtures";
import type { Page, Locator } from "@playwright/test";
import { FOCUS_VIDEO } from "../tests/fixtures/mocks";

function videoItem(page: Page): Locator {
  return page.locator(`[data-media="${FOCUS_VIDEO}"]`);
}

function playOverlay(page: Page): Locator {
  return videoItem(page).getByRole("button", { name: "Play video" });
}

async function openEditor(page: Page) {
  await page.goto("/editor");
  await expect(page.getByText("South America")).toBeVisible({
    timeout: 15_000,
  });
}

async function scrollToVideo(page: Page) {
  const nav = page.getByRole("navigation");
  const santiago = nav.getByText("Santiago");

  if (!(await santiago.isVisible())) {
    await nav.getByText("Chile").click();
    await expect(santiago).toBeVisible({ timeout: 3_000 });
  }

  await santiago.click();
  await expect(videoItem(page)).toBeVisible({ timeout: 5_000 });
}

test.describe("Video keyboard controls", () => {
  test.beforeEach(async ({ focusPage: page }) => {
    await page.addInitScript(() => {
      HTMLVideoElement.prototype.play = function () {
        this.dispatchEvent(new Event("play"));
        return Promise.resolve();
      };
      HTMLVideoElement.prototype.pause = function () {
        this.dispatchEvent(new Event("pause"));
      };
      HTMLVideoElement.prototype.load = function () {};
    });
    await openEditor(page);
  });

  test("space starts video when item is selected", async ({
    focusPage: page,
  }) => {
    await scrollToVideo(page);

    // Select the photo before the video, then arrow into it
    await page.locator('[data-media="focus-photo-10.jpg"]').click();
    await page.keyboard.press("ArrowRight");
    await expect(videoItem(page)).toHaveAttribute("aria-pressed", "true");

    // Focus and press Space to start playback
    await videoItem(page).focus();
    await videoItem(page).press("Space");

    await expect(playOverlay(page)).toBeHidden({ timeout: 3_000 });
  });

  test("arrow keys do not navigate away from playing video", async ({
    focusPage: page,
  }) => {
    await scrollToVideo(page);

    // Start video via play overlay
    await playOverlay(page).click();
    await expect(playOverlay(page)).toBeHidden({ timeout: 3_000 });
    await expect(videoItem(page)).toHaveAttribute("aria-pressed", "true");

    await page.waitForTimeout(200);

    // Arrow keys should not change selection while video is playing
    await page.keyboard.press("ArrowRight");

    await expect(videoItem(page)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[aria-pressed="true"]')).toHaveCount(1);
  });
});
