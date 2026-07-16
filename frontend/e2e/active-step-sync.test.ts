import {
  ensureExternalMediaOpen,
  externalMediaCorsHeaders,
  externalMediaImportButton,
  test,
  expect,
} from "./fixtures";
import type { Page } from "@playwright/test";

async function pageTopIsVisibleBelowHeader(page: Page, text: string) {
  return page.evaluate((targetText) => {
    const pageEl = Array.from(
      document.querySelectorAll<HTMLElement>(".page-container.step-main"),
    ).find((el) => el.textContent?.includes(targetText));
    const headerEl = document.querySelector<HTMLElement>(".editor-header");
    if (!pageEl || !headerEl) return false;
    const pageTop = pageEl.getBoundingClientRect().top;
    return (
      pageTop >= headerEl.getBoundingClientRect().bottom &&
      pageTop < window.innerHeight
    );
  }, text);
}

async function expectPageVisibleBelowHeader(page: Page, text: string) {
  await expect.poll(() => pageTopIsVisibleBelowHeader(page, text)).toBe(true);
}

async function clickNavStep(page: Page, stepId: number) {
  const nav = page.getByRole("navigation");
  const step = nav.locator(`[data-nav-step="${stepId}"]`);
  await step.scrollIntoViewIfNeeded();
  await expect(step).toBeVisible({ timeout: 3_000 });
  await step.click();
}

test.describe("Active step sync", () => {
  test("nav click keeps viewer, nav active state, and inspector target aligned", async ({
    focusPage: page,
  }) => {
    await page.goto("/editor");
    await expect(page.getByRole("main").getByText("South America")).toBeVisible({
      timeout: 15_000,
    });

    const beforeClickScrollY = await page.evaluate(() => window.scrollY);
    await clickNavStep(page, 102);
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(beforeClickScrollY + 100);
    await expect(
      page.locator(".album-container").getByText("Ushuaia").first(),
    ).toBeVisible();
    await expectPageVisibleBelowHeader(page, "Ushuaia");
    await clickNavStep(page, 103);
    await expect(
      page.locator(".album-container").getByText("Santiago").first(),
    ).toBeVisible();
    await clickNavStep(page, 101);
    await expect(
      page.locator(".album-container").getByText("Buenos Aires").first(),
    ).toBeVisible();
    await expectPageVisibleBelowHeader(page, "Buenos Aires");
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
    await expect.poll(() => importedStepId).toBe("101");
  });
});
