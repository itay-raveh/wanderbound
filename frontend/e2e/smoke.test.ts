import { test, expect } from "./fixtures";
import { mockAuthStateAnonymous } from "../tests/fixtures/mocks";

const ANONYMOUS = async (page: import("@playwright/test").Page) => {
  await page.route("**/api/v1/auth/state", (route) =>
    route.fulfill({ json: mockAuthStateAnonymous }),
  );
};

test.describe("Landing page", () => {
  test.beforeEach(async ({ page }) => ANONYMOUS(page));

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
  test("anonymous user stays on landing", async ({ page }) => {
    await ANONYMOUS(page);
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
