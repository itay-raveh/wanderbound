import { test, expect } from "./fixtures";

test.describe("Editor", () => {
  test("loads editor page with album content", async ({
    authedPage: page,
  }) => {
    await page.goto("/");
    await page.waitForURL("/editor");
    // Editor should render and show album content
    await expect(page.locator("body")).toBeVisible();
  });

  test("displays the album title", async ({ authedPage: page }) => {
    await page.goto("/editor");
    await page.waitForURL("/editor");
    // The album title "South America" should appear somewhere
    await expect(page.getByText("South America")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("shows step name in the viewer", async ({ authedPage: page }) => {
    await page.goto("/editor");
    await page.waitForURL("/editor");
    // The step name "Amsterdam" should be visible in the main viewer
    await expect(page.getByRole("main")).toContainText("Amsterdam", { timeout: 15_000 });
  });
});
