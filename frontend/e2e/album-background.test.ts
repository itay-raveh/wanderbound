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
      if (rtl)
        await page.getByRole("button", { name: "הצגת המאפיינים" }).click();
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
    const darkMuted = await paper
      .locator(".coords")
      .evaluate((element) => getComputedStyle(element).color);
    expect(darkMuted).not.toBe("rgb(255, 255, 255)");
    await paper.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("editor.png") });
    if (rtl)
      await page.getByRole("button", { name: "הסתרת המאפיינים" }).click();
    await paper.screenshot({ path: testInfo.outputPath("paper.png") });
    await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
      route.fulfill({
        json: {
          album: { ...album, media: mockMedia },
          steps: mockSteps,
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
    await page.screenshot({
      path: testInfo.outputPath("print.png"),
      fullPage: true,
    });
    await page.pdf({
      path: testInfo.outputPath("album.pdf"),
      printBackground: true,
      preferCSSPageSize: true,
    });
  });
}
