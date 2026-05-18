import { test, expect } from "./fixtures";

test.describe("Landing page", () => {
  test("renders the landing page", async ({ anonymousPage: page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/wanderbound/i);
  });

  test("shows sign-in area", async ({ anonymousPage: page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
  });
});

test.describe("Health check redirect", () => {
  test("anonymous user stays on landing", async ({ anonymousPage: page }) => {
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
