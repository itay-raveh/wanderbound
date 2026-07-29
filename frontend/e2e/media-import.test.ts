import {
  ensureExternalMediaOpen,
  externalMediaCorsHeaders,
  externalMediaImportButton,
  test,
  expect,
} from "./fixtures";
import { mockMedia, mockStep, TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const API = "**/api/v1";
const IMPORTED =
  "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg";

function unusedDrawer(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Unused" });
}

async function ensureUnusedTrayVisible(page: import("@playwright/test").Page) {
  const drawer = unusedDrawer(page);
  const count = drawer.getByText(/^\d+$/);
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await expect(count).toBeVisible({ timeout: 15_000 });
}

async function mockDeviceImport(
  page: import("@playwright/test").Page,
  onImport: () => void,
) {
  await page.route(
    `${API}/albums/*/external-media/add/device`,
    async (route) => {
      const headers = externalMediaCorsHeaders(page);
      if (route.request().method() === "OPTIONS") {
        await route.fulfill({ headers: headers.cors, status: 204 });
        return;
      }
      onImport();
      await route.fulfill({
        headers: headers.json,
        status: 200,
        body: JSON.stringify({ type: "import_completed", names: [IMPORTED] }),
      });
    },
  );
}

async function selectImportStep(
  page: import("@playwright/test").Page,
  stepId: number,
) {
  await page.locator(`[data-nav-step="${stepId}"]`).click();
  await ensureExternalMediaOpen(page);
  await expect(
    page.getByLabel("Inspector").getByText(`Import to ${mockStep.name}`),
  ).toBeVisible();
  await expect(externalMediaImportButton(page)).toBeVisible();
}

test.describe("Media import", () => {
  test.describe.configure({ timeout: 60_000 });

  test("device import into a step appears in the unused tray", async ({
    authedPage: page,
  }) => {
    let imported = false;

    await mockDeviceImport(page, () => {
      imported = true;
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
    await expect(page.getByRole("main").getByText("South America")).toBeVisible(
      {
        timeout: 15_000,
      },
    );
    await selectImportStep(page, 1);
    await ensureExternalMediaOpen(page);

    const fileChooser = page.waitForEvent("filechooser");
    await externalMediaImportButton(page).click();
    const importResponse = page.waitForResponse(
      (res) =>
        res.url().includes("/api/v1/albums/") &&
        res.url().endsWith("/external-media/add/device") &&
        res.request().method() === "POST",
    );
    const chooser = await fileChooser;
    await chooser.setFiles({
      name: "import.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from(TINY_JPEG_BASE64, "base64"),
    });
    expect((await importResponse).ok()).toBeTruthy();
    expect(imported).toBe(true);

    await ensureUnusedTrayVisible(page);
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
});
