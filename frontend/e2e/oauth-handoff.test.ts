import { expect, test } from "./fixtures";

test.describe("OAuth pending-signup handoff", () => {
  test("pending_signup state sends user to /upload and renders the upload card", async ({
    pendingSignupPage: page,
  }) => {
    await page.goto("/");
    await page.waitForURL("/upload");
    await expect(
      page.getByRole("button", { name: /drop your file/i }),
    ).toBeVisible();
  });
});
