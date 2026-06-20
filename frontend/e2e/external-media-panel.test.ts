import {
  ensureExternalMediaOpen,
  externalMediaImportButton,
  test,
  expect,
} from "./fixtures";

test.describe("External media panel", () => {
  test("shows source status, upgrade action, and import target", async ({
    editorPage: page,
  }) => {
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Expand", exact: true }).click();
    await page.locator('[data-nav-step="1"]').click();

    await ensureExternalMediaOpen(page);
    await expect(externalMediaImportButton(page)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Upgrade Media" }),
    ).toBeVisible();
    await expect(page.getByText("Import to Amsterdam")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Replace selected media/i }),
    ).not.toBeVisible();
  });
});
