import {
  ensureExternalMediaOpen,
  externalMediaCorsHeaders,
  externalMediaImportButton,
  test,
  expect,
} from "./fixtures";
import type { Page } from "@playwright/test";

const NAV_SCROLL_MIN_TOP_CLEARANCE = 48;
const NAV_SCROLL_MAX_TOP_CLEARANCE = 88;

async function pageTopBelowHeader(page: Page, text: string) {
  return page.evaluate((targetText) => {
    const pageEl = Array.from(
      document.querySelectorAll<HTMLElement>(".page-container.step-main"),
    ).find((el) => el.textContent?.includes(targetText));
    const headerEl = document.querySelector<HTMLElement>(".editor-header");
    if (!pageEl || !headerEl) return Number.NEGATIVE_INFINITY;
    return Math.round(
      pageEl.getBoundingClientRect().top -
        headerEl.getBoundingClientRect().bottom,
    );
  }, text);
}

test.describe("Active step sync", () => {
  test("nav click keeps viewer, nav active state, and inspector target aligned", async ({
    focusPage: page,
  }) => {
    await page.goto("/editor");
    await expect(page.getByRole("main").getByText("South America")).toBeVisible({
      timeout: 15_000,
    });

    const nav = page.getByRole("navigation");
    const beforeClickScrollY = await page.evaluate(() => window.scrollY);
    await nav.locator('[data-nav-step="102"]').click();
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(beforeClickScrollY + 100);
    await expect(
      page.locator(".album-container").getByText("Ushuaia").first(),
    ).toBeVisible();
    await expect
      .poll(() => pageTopBelowHeader(page, "Ushuaia"))
      .toBeGreaterThanOrEqual(NAV_SCROLL_MIN_TOP_CLEARANCE);
    await expect
      .poll(() => pageTopBelowHeader(page, "Ushuaia"))
      .toBeLessThanOrEqual(NAV_SCROLL_MAX_TOP_CLEARANCE);
    await nav.locator('[data-nav-step="103"]').click();
    await expect(
      page.locator(".album-container").getByText("Santiago").first(),
    ).toBeVisible();
    await nav.locator('[data-nav-step="101"]').click();
    await expect(
      page.locator(".album-container").getByText("Buenos Aires").first(),
    ).toBeVisible();
    await expect
      .poll(() => pageTopBelowHeader(page, "Buenos Aires"))
      .toBeGreaterThanOrEqual(NAV_SCROLL_MIN_TOP_CLEARANCE);
    await expect
      .poll(() => pageTopBelowHeader(page, "Buenos Aires"))
      .toBeLessThanOrEqual(NAV_SCROLL_MAX_TOP_CLEARANCE);
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
