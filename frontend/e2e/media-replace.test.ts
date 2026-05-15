import { test, expect } from "./fixtures";
import { TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const API = "**/api/v1";

async function ensureExternalMediaOpen(
  page: import("@playwright/test").Page,
) {
  const toggle = page.getByRole("button", {
    name: /Expand "External media"|Collapse "External media"/,
  });
  await expect(toggle).toBeVisible({ timeout: 15_000 });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") {
    await toggle.click();
  }
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

test.describe("External media replacement", () => {
  test("cover media can be selected for replacement", async ({
    authedPage: page,
  }) => {
    await page.goto("/editor");
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
    await page.locator('[data-media="cover.jpg"]').click({
      position: { x: 20, y: 20 },
    });
    await ensureExternalMediaOpen(page);
    await expect(
      page.getByRole("button", { name: /Replace selected media/i }),
    ).toBeEnabled();
  });

  test("replaces focused media from a device file", async ({
    authedPage: page,
  }) => {
    await page.route(`${API}/albums/*/external-media/replace/device`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          name: "photo1.jpg",
          kind: "photo",
          storage_path: "photo1.jpg",
          width: 3000,
          height: 2000,
          byte_size: 12345,
          source_ref_id: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto("/editor");
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Expand", exact: true }).click();
    await page.locator('[data-nav-step="1"]').click();
    await page
      .locator('[data-media="photo2.jpg"]')
      .getByRole("button", { name: "Replace with better quality" })
      .click();
    await ensureExternalMediaOpen(page);
    await expect(
      page.getByRole("button", { name: /Replace selected media/i }),
    ).toBeEnabled();
    await page.getByRole("button", { name: /Replace selected media/i }).click();
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("menuitem", { name: "Device" }).click();
    await (await chooser).setFiles({
      name: "better.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from(TINY_JPEG_BASE64, "base64"),
    });
    const reviewDialog = page.locator(".review-dialog");
    await expect(reviewDialog).toBeVisible();
    await expect(page.getByText("Review replacement")).toBeVisible();
    await expect(
      reviewDialog.getByRole("button", { name: /Replace everywhere/i }),
    ).toBeVisible();
    await reviewDialog.getByRole("button", { name: /Replace everywhere/i }).click();
    await expect(page.getByText(/Media replaced/i)).toBeVisible();
  });
});
