import {
  ensureExternalMediaOpen,
  externalMediaCorsHeaders,
  externalMediaImportButton,
  test,
  expect,
} from "./fixtures";

test.describe("Active step sync", () => {
  test("nav click keeps viewer, nav active state, and inspector target aligned", async ({
    focusPage: page,
  }) => {
    await page.goto("/editor");
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });

    const nav = page.getByRole("navigation");
    await nav.getByText("Argentina").click();
    await nav.locator('[data-nav-step="102"]').click();
    await expect(
      page.getByLabel("Inspector").getByRole("region", { name: "Unused" }),
    ).toBeVisible();

    let importedStepId: string | null = null;
    await page.route(
      "**/api/v1/albums/*/external-media/add/device",
      async (route) => {
        const headers = externalMediaCorsHeaders(page);
        if (route.request().method() === "OPTIONS") {
          await route.fulfill({ headers: headers.cors, status: 204 });
          return;
        }
        const form = route.request().postDataBuffer();
        importedStepId =
          form.toString("utf8").match(/name="step_id"\r\n\r\n(\d+)/)?.[1] ??
          null;
        await route.fulfill({
          headers: headers.json,
          status: 200,
          body: JSON.stringify({ type: "import_completed", names: [] }),
        });
      },
    );

    const fileChooser = page.waitForEvent("filechooser");
    await ensureExternalMediaOpen(page);
    await expect(externalMediaImportButton(page)).toBeVisible();
    await externalMediaImportButton(page).click();
    const chooser = await fileChooser;
    await chooser.setFiles({
      name: "import.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect.poll(() => importedStepId).toBe("102");
  });
});
