import type { Locator } from "@playwright/test";
import { readFileSync } from "node:fs";
import { expect, openEditor, test } from "./fixtures";
import {
  mockAlbum,
  mockAuthStateAuthenticated,
  mockMedia,
  mockSteps,
  mockUser,
} from "../tests/fixtures/mocks";

const photo = readFileSync(
  new URL(
    "../../fixtures/demo/trip/south-america-2024-2025_14232450/beagle-channel_191160695/photos/e0236637-9397-4d62-af82-d9ddf93f828a_1f644dad-4b66-4590-b98c-c4a10aab6383.jpg",
    import.meta.url,
  ),
);

// Composite the translucent toolbar and hover fill over both extremes of
// photo/paper artwork; every intermediate backdrop must also stay readable.
async function expectActionContrast(action: Locator, focus = false) {
  const contrast = await action.evaluate((element, focus) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const context = canvas.getContext("2d", { willReadFrequently: true })!;
    const style = getComputedStyle(element);
    const toolbar = getComputedStyle(element.closest(".album-actions")!);
    context.fillStyle = focus ? style.outlineColor : style.color;
    context.fillRect(0, 0, 1, 1);
    const foreground = Array.from(context.getImageData(0, 0, 1, 1).data);
    const luminance = (rgb: number[]) =>
      rgb.slice(0, 3).reduce((sum, value, index) => {
        const channel = value / 255;
        return (
          sum +
          [0.2126, 0.7152, 0.0722][index] *
            (channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4)
        );
      }, 0);
    return Math.min(
      ...["black", "white"].map((backdrop) => {
        for (const color of [
          backdrop,
          toolbar.backgroundColor,
          style.backgroundColor,
        ]) {
          context.fillStyle = color;
          context.fillRect(0, 0, 1, 1);
        }
        const background = Array.from(context.getImageData(0, 0, 1, 1).data);
        const values = [luminance(foreground), luminance(background)];
        return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05);
      }),
    );
  }, focus);
  expect(contrast).toBeGreaterThanOrEqual(3);
}

for (const { rtl, width } of [
  { rtl: false, width: 1600 },
  { rtl: true, width: 1024 },
]) {
  test(`paper color persists, resets and prints with readable text (${rtl ? "Hebrew" : "English"}, ${width}px)`, async ({
    authedPage: page,
  }, testInfo) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({
      colorScheme: rtl ? "dark" : "light",
      reducedMotion: "reduce",
    });
    const user = { ...mockUser, locale: rtl ? "he" : "en-US" };
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ json: user }),
    );
    await page.route("**/api/v1/auth/state", (route) =>
      route.fulfill({ json: { ...mockAuthStateAuthenticated, user } }),
    );
    const album = {
      ...mockAlbum,
      background_color: null as string | null,
      show_page_numbers: true,
      hidden_headers: ["full-map"],
    };
    const tileText = rtl ? "יום של טיול בתעלות" : "A day exploring the canals";
    const steps = mockSteps.map((step) => ({
      ...step,
      pages: step.pages.map((page) => ({
        ...page,
        slots: [
          ...page.slots,
          {
            id: "paper-contrast-text",
            kind: "text",
            text: tileText,
            frame_orientation: "landscape",
            continuation_priority: 100,
          },
        ],
      })),
    }));
    await page.route("**/api/v1/albums/aid-1/steps", (route) =>
      route.fulfill({ json: steps }),
    );
    const photoMedia = mockMedia.map((media) => ({
      ...media,
      aid: "aid-1",
      uid: 1,
      kind: "photo",
    }));
    await page.route("**/api/v1/albums/aid-1/media", (route) =>
      route.fulfill({ json: photoMedia }),
    );
    const textTile = page.locator(".page-content .text-item").first();
    const expectTextTile = async (background: string, color: string) => {
      await expect(textTile).toHaveCSS("background-color", background);
      await expect(textTile.locator(".tile-text")).toHaveCSS("color", color);
      await expect(textTile.locator(".tile-text")).toHaveCSS(
        "direction",
        rtl ? "rtl" : "ltr",
      );
    };
    const expectActions = async () => {
      for (const action of [
        textTile.locator(".album-action"),
        page.locator(".page-content .photo-item .album-action").first(),
      ]) {
        await expect(action).toBeVisible();
        await page.mouse.move(0, 0);
        await expectActionContrast(action);
        await action.hover();
        await expectActionContrast(action);
        await page.keyboard.press("Tab");
        await action.focus();
        await expect(action).toHaveCSS("outline-style", "solid");
        await expectActionContrast(action, true);
      }
    };
    const updates: unknown[] = [];
    await page.route("**/api/v1/albums/aid-1", async (route) => {
      if (route.request().method() === "PATCH") {
        const update = route.request().postDataJSON();
        updates.push(update);
        Object.assign(album, update);
      }
      await route.fulfill({ json: album });
    });
    await page.route("**/api/v1/albums/*/media/*", (route) =>
      route.fulfill({ contentType: "image/jpeg", body: photo }),
    );
    await page.route("**/weather-icons/cloudy.svg", (route) =>
      route.fulfill({
        path: new URL(
          "../public/weather-icons/overcast-day.svg",
          import.meta.url,
        ).pathname,
        contentType: "image/svg+xml",
      }),
    );
    await openEditor(page);
    const showProperties = async () => {
      await page
        .locator("#editor-inspector .panel-section-header")
        .filter({ hasText: rtl ? "מאפיינים" : "Properties" })
        .click();
    };
    await showProperties();
    const background = page.getByRole("button", {
      name: rtl ? "רקע העמודים" : "Page background",
      exact: true,
    });
    const paper = page
      .locator(".page-container")
      .filter({ has: page.locator(".step-main") })
      .first();
    const defaultColor = rtl ? "rgb(35, 35, 56)" : "rgb(255, 255, 255)";
    await expect(background.locator(".color-swatch")).toHaveCSS(
      "background-color",
      defaultColor,
    );
    const defaultMuted = await paper
      .locator(".coords")
      .evaluate((element) => getComputedStyle(element).color);
    await background.focus();
    await page.keyboard.press("Enter");
    const hex = page.locator(".q-color-picker__header input");
    await hex.fill("#ffeeaa");
    await hex.press("Tab");
    await expect.poll(() => updates).toEqual([{ background_color: "#ffeeaa" }]);
    await page.keyboard.press("Escape");
    await expect(background).toBeFocused();
    await expect(paper).toHaveCSS("background-color", "rgb(255, 238, 170)");
    await expect(paper.locator(".step-main")).toHaveCSS(
      "color",
      "rgb(0, 0, 0)",
    );
    await expectTextTile("rgb(255, 238, 170)", "rgb(0, 0, 0)");
    await expectActions();
    const lightMuted = await paper
      .locator(".coords")
      .evaluate((element) => getComputedStyle(element).color);
    expect(lightMuted).not.toBe("rgb(0, 0, 0)");
    if (rtl)
      await page.getByRole("button", { name: "הסתרת המאפיינים" }).click();
    await paper.screenshot({ path: testInfo.outputPath("light-paper.png") });
    expect(album.colors).toEqual(mockAlbum.colors);
    await page.reload();
    await showProperties();
    await expect(background.locator(".color-swatch")).toHaveCSS(
      "background-color",
      "rgb(255, 238, 170)",
    );
    const reset = page.getByRole("button", {
      name: rtl ? "איפוס" : "Reset",
      exact: true,
    });
    await reset.click();
    await expect(paper).toHaveCSS("background-color", defaultColor);
    await expect(paper.locator(".coords")).toHaveCSS("color", defaultMuted);
    await expectActions();
    await page.keyboard.press("Control+z");
    await expect(paper).toHaveCSS("background-color", "rgb(255, 238, 170)");
    await background.click();
    await hex.fill("#ff0000");
    await hex.press("Tab");
    await page.keyboard.press("Escape");
    await expect(paper.locator(".step-main")).toHaveCSS(
      "color",
      "rgb(0, 0, 0)",
    );
    await background.click();
    await hex.fill("#202040");
    await hex.press("Tab");
    await page.keyboard.press("Escape");
    await expect(paper.locator(".step-main")).toHaveCSS(
      "color",
      "rgb(255, 255, 255)",
    );
    await expect(paper.locator(".album-page-number")).toHaveCSS(
      "color",
      "rgb(240, 240, 245)",
    );
    await expectTextTile("rgb(32, 32, 64)", "rgb(255, 255, 255)");
    await expectActions();
    await background.click();
    await hex.fill("#172033");
    await hex.press("Tab");
    await page.keyboard.press("Escape");
    await expectActions();
    await background.click();
    await hex.fill("#202040");
    await hex.press("Tab");
    await page.keyboard.press("Escape");
    const darkMuted = await paper
      .locator(".coords")
      .evaluate((element) => getComputedStyle(element).color);
    expect(darkMuted).not.toBe("rgb(255, 255, 255)");
    await paper.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("editor.png") });
    if (rtl)
      await page.getByRole("button", { name: "הסתרת המאפיינים" }).click();
    await paper.screenshot({ path: testInfo.outputPath("paper.png") });
    await textTile.locator(".tile-display").click();
    await expect(textTile.locator("textarea")).toHaveValue(tileText);
    await expectTextTile("rgb(32, 32, 64)", "rgb(255, 255, 255)");
    await textTile.locator("textarea").press("Escape");
    await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
      route.fulfill({
        json: {
          album: { ...album, media: photoMedia },
          steps,
          segments: [],
          total_distance_km: 0,
        },
      }),
    );
    await page.route("**/api/v1/albums/*/media/*", (route) =>
      route.fulfill({
        contentType: "image/jpeg",
        body: photo,
      }),
    );
    await page.goto("/print/aid-1");
    await page.waitForFunction(() => {
      const state = window as unknown as Record<string, unknown>;
      return state.__PRINT_READY__ || state.__PRINT_ERROR__;
    });
    expect(
      await page.evaluate(
        () => (window as unknown as Record<string, unknown>).__PRINT_ERROR__,
      ),
    ).toBeUndefined();
    const printPaper = page
      .locator(".page-container")
      .filter({ has: page.locator(".step-main") })
      .first();
    await expect(printPaper).toHaveCSS("background-color", "rgb(32, 32, 64)");
    await expect(printPaper.locator(".step-main")).toHaveCSS(
      "color",
      "rgb(255, 255, 255)",
    );
    await expect(printPaper.locator(".coords")).toHaveCSS("color", darkMuted);
    await expectTextTile("rgb(32, 32, 64)", "rgb(255, 255, 255)");
    await page.screenshot({
      path: testInfo.outputPath("print.png"),
      fullPage: true,
    });
    await page.pdf({
      path: testInfo.outputPath("album.pdf"),
      printBackground: true,
      preferCSSPageSize: true,
    });
    album.background_color = "#ffeeaa";
    await page.reload();
    await page.waitForFunction(
      () => (window as unknown as Record<string, unknown>).__PRINT_READY__,
    );
    await expectTextTile("rgb(255, 238, 170)", "rgb(0, 0, 0)");
    await page.pdf({
      path: testInfo.outputPath("light-album.pdf"),
      printBackground: true,
      preferCSSPageSize: true,
    });
  });
}
