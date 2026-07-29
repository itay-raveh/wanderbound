import { test } from "./fixtures";

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
