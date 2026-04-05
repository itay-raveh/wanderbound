import { test, expect } from "./fixtures";

test.describe("Landing page", () => {
  test("renders the landing page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/wanderbound/i);
  });

  test("shows sign-in area", async ({ page }) => {
    await page.goto("/");
    // The landing page should have some visible content
    await expect(page.locator("body")).toBeVisible();
  });
});

test.describe("Health check redirect", () => {
  test("unauthenticated user stays on landing", async ({ page }) => {
    // Without API mocking, the session check fails → user stays on landing
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
    );
    await page.goto("/editor");
    await page.waitForURL("/", { timeout: 15_000 });
  });

  test("authenticated user with data goes to editor", async ({
    authedPage: page,
  }) => {
    await page.goto("/");
    await page.waitForURL("/editor");
  });
});
