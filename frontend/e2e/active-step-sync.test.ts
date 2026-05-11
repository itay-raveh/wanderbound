import { test, expect } from "./fixtures";

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

    let importedStepId: string | null = null;
    await page.route(
      "**/api/v1/albums/*/media-imports/device",
      async (route) => {
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
        const form = route.request().postDataBuffer();
        importedStepId =
          form.toString("utf8").match(/name="step_id"\r\n\r\n(\d+)/)?.[1] ??
          null;
        await route.fulfill({
          headers: { ...headers, "content-type": "application/json" },
          status: 200,
          body: JSON.stringify({ type: "import_completed", names: [] }),
        });
      },
    );

    const fileChooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add media" }).click();
    await page.getByRole("menuitem", { name: "Device" }).click();
    const chooser = await fileChooser;
    await chooser.setFiles({
      name: "import.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect.poll(() => importedStepId).toBe("102");
  });
});
