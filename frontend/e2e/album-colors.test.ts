import { expect, openEditor, test } from "./fixtures";
import {
  mockAlbum,
  mockUser,
  mockAuthStateAuthenticated,
} from "../tests/fixtures/mocks";

for (const width of [1600, 1024]) {
  test(`color picker commits on blur and supports undo at ${width}px`, async ({
    authedPage: page,
  }) => {
    const rtl = width === 1024;
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
      colors: { ...mockAlbum.colors, fr: "#336699" },
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
    await openEditor(page);
    if (rtl)
      await page.getByRole("button", { name: "הצגת המאפיינים" }).click();
    const country = page.getByRole("button", {
      name: rtl ? "הולנד · צבעי הדגשה" : "Netherlands · Accent colors",
    });
    await country.focus();
    await page.keyboard.press("Enter");
    const picker = page.locator(".q-color-picker");
    const hex = picker.locator(".q-color-picker__header input");
    await hex.fill("#123456");
    expect(updates).toHaveLength(0);
    await hex.press("Tab");
    await expect
      .poll(() => updates)
      .toEqual([{ colors: { nl: "#123456", fr: "#336699" } }]);
    await page.keyboard.press("Escape");
    await expect(picker).toBeHidden();
    await expect(country).toBeFocused();
    await expect(country.locator(".color-swatch")).toHaveCSS(
      "background-color",
      "rgb(18, 52, 86)",
    );
    await page.keyboard.press("Control+z");
    await expect(country.locator(".color-swatch")).toHaveCSS(
      "background-color",
      "rgb(231, 124, 49)",
    );
    await expect.poll(() => updates.length).toBe(2);
    expect(album.colors).toEqual({ ...mockAlbum.colors, fr: "#336699" });
  });
}
