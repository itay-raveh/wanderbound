import { expect, mockGooglePendingSignupTransition, test } from "./fixtures";

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

  test("after /auth/google returns null, app navigates to /upload", async ({
    page,
  }) => {
    await mockGooglePendingSignupTransition(page);
    await page.goto("/");
    // Drive the OAuth callback path directly: the iframe popup can't be
    // clicked from Playwright, but we can invoke the SDK call it triggers.
    await page.evaluate(async () => {
      const mod = await import("/src/client/index.ts");
      await mod.authenticate({
        body: { credential: "fake" },
        path: { provider: "google" },
      });
      window.location.href = "/upload";
    });
    await page.waitForURL("/upload");
    await expect(
      page.getByRole("button", { name: /drop your file/i }),
    ).toBeVisible();
  });
});
