import { test, expect } from "./fixtures";
import {
  mockAlbum,
  mockMedia,
  mockStep,
  mockUser,
} from "../tests/fixtures/mocks";

const API = "**/api/v1";
const IMPORTED =
  "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg";

function unusedDrawer(page: import("@playwright/test").Page) {
  return page.getByLabel("Inspector").filter({ hasText: "Unused" });
}

test.describe("Media import", () => {
  test("device import into a step appears in the unused tray", async ({
    authedPage: page,
  }) => {
    let imported = false;

    await page.route(`${API}/albums/*/media-imports/device`, async (route) => {
      const headers = {
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "*",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-origin": new URL(page.url()).origin,
      };
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ headers, status: 204 });
        return;
      }
      imported = true;
      await route.fulfill({
        headers: {
          ...headers,
          "content-type": "application/json",
        },
        status: 200,
        body: JSON.stringify({ type: "import_completed", names: [IMPORTED] }),
      });
    });
    await page.route(`${API}/albums/*/steps`, async (route) => {
      const steps = imported
        ? [{ ...mockStep, unused: [IMPORTED, ...mockStep.unused] }]
        : [mockStep];
      await route.fulfill({ json: steps });
    });
    await page.route(`${API}/albums/*/media`, async (route) => {
      const media = imported
        ? [...mockMedia, { name: IMPORTED, width: 640, height: 480 }]
        : mockMedia;
      await route.fulfill({ json: media });
    });

    await page.goto("/editor");
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Expand", exact: true }).click();
    await page.locator('[data-nav-step="1"]').click();
    await expect(
      unusedDrawer(page).getByText("0", { exact: true }),
    ).toBeVisible();

    const fileChooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add media" }).click();
    await page.getByRole("menuitem", { name: "Device" }).click();
    const importResponse = page.waitForResponse(
      (res) =>
        res.url().includes("/api/v1/albums/") &&
        res.url().endsWith("/media-imports/device") &&
        res.request().method() === "POST",
    );
    const chooser = await fileChooser;
    await chooser.setFiles({
      name: "import.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    expect((await importResponse).ok()).toBeTruthy();
    expect(imported).toBe(true);

    await expect(
      unusedDrawer(page).getByText("1", { exact: true }),
    ).toBeVisible({
      timeout: 5_000,
    });
    const importedImage = page.locator(`[data-media="${IMPORTED}"] img`);
    await expect(importedImage).toBeVisible();
    await expect(importedImage).toHaveAttribute("src", /11111111/);
    await expect
      .poll(() =>
        importedImage.evaluate((img) => (img as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
  });

  test("step import overlay resets when changing albums", async ({
    authedPage: page,
  }) => {
    let imported = false;

    await page.route(`${API}/users`, (route) =>
      route.fulfill({
        json: { ...mockUser, album_ids: ["aid-1", "aid-2"] },
      }),
    );
    await page.route(`${API}/albums/*`, (route) => {
      const aid = new URL(route.request().url()).pathname
        .split("/albums/")[1]
        ?.split("/")[0];
      return route.fulfill({
        json: {
          ...mockAlbum,
          id: aid,
          title: aid === "aid-2" ? "Second Album" : mockAlbum.title,
        },
      });
    });
    await page.route(`${API}/albums/*/steps`, (route) =>
      route.fulfill({ json: [mockStep] }),
    );
    await page.route(`${API}/albums/*/media`, (route) => {
      const aid = new URL(route.request().url()).pathname
        .split("/albums/")[1]
        ?.split("/")[0];
      const media =
        imported && aid === "aid-1"
          ? [...mockMedia, { name: IMPORTED, width: 640, height: 480 }]
          : mockMedia;
      return route.fulfill({ json: media });
    });
    await page.route(`${API}/albums/*/media-imports/device`, async (route) => {
      const headers = {
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "*",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-origin": new URL(page.url()).origin,
      };
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ headers, status: 204 });
        return;
      }
      imported = true;
      await route.fulfill({
        headers: {
          ...headers,
          "content-type": "application/json",
        },
        status: 200,
        body: JSON.stringify({ type: "import_completed", names: [IMPORTED] }),
      });
    });

    await page.goto("/editor");
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Expand", exact: true }).click();
    await page.locator('[data-nav-step="1"]').click();
    await expect(
      unusedDrawer(page).getByText("0", { exact: true }),
    ).toBeVisible();

    const fileChooser = page.waitForEvent("filechooser");
    await page
      .getByRole("button", { name: "Add media" })
      .click({ force: true });
    await expect(page.getByRole("menuitem", { name: "Device" })).toBeVisible();
    await page.getByRole("menuitem", { name: "Device" }).click();
    const chooser = await fileChooser;
    await chooser.setFiles({
      name: "import.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect(
      unusedDrawer(page).getByText("1", { exact: true }),
    ).toBeVisible({
      timeout: 5_000,
    });

    await page.getByLabel("Select album").click();
    await page.getByRole("option", { name: "Aid 2" }).click();
    await page.getByRole("button", { name: "Expand", exact: true }).click();
    await page.locator('[data-nav-step="1"]').click();

    await expect(
      unusedDrawer(page).getByText("0", { exact: true }),
    ).toBeVisible({
      timeout: 5_000,
    });
  });
});
