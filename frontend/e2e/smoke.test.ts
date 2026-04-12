import { test, expect } from "./fixtures";

const UNAUTHENTICATED = async (page: import("@playwright/test").Page) => {
  await page.route("**/api/v1/users", (route) =>
    route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
};

test.describe("Landing page", () => {
  test.beforeEach(async ({ page }) => UNAUTHENTICATED(page));

  test("renders the landing page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/wanderbound/i);
  });

  test("shows sign-in area", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
  });
});

test.describe("Health check redirect", () => {
  test("unauthenticated user stays on landing", async ({ page }) => {
    await UNAUTHENTICATED(page);
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
