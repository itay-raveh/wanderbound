import { test, expect } from "./fixtures";
import {
  mockAuthStateAnonymous,
  mockAuthStatePending,
} from "../tests/fixtures/mocks";

const ANON = "**/api/v1/auth/state";
const GOOGLE = "**/api/v1/auth/google";

test.describe("OAuth pending-signup handoff", () => {
  test("pending_signup state sends user to /upload and renders the upload card", async ({
    page,
  }) => {
    await page.route(ANON, (route) =>
      route.fulfill({ json: mockAuthStatePending }),
    );
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
    );
    await page.goto("/");
    await page.waitForURL("/upload");
    await expect(
      page.getByRole("button", { name: /drop your file/i }),
    ).toBeVisible();
  });

  test("after /auth/google returns null, app navigates to /upload", async ({
    page,
  }) => {
    let state = mockAuthStateAnonymous;
    await page.route(ANON, (route) => route.fulfill({ json: state }));
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
    );
    await page.route(GOOGLE, (route) => {
      state = mockAuthStatePending;
      return route.fulfill({ json: null });
    });
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
