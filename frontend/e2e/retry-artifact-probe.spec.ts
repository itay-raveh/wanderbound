import { expect, test } from "@playwright/test";

test("controlled failure diagnostics survive a successful retry", async ({
  page,
}, testInfo) => {
  await page.setContent("<h1>Retry artifact verification</h1>");
  await expect(page.getByRole("heading")).toHaveText(
    testInfo.retry === 0
      ? "Deliberate first-attempt mismatch"
      : "Retry artifact verification",
    { timeout: 150 },
  );
});
