import { test, expect } from "./fixtures";
import { mockUser } from "../tests/fixtures/mocks";

test.describe("Editor", () => {
  test("replaces an unavailable saved album before loading it", async ({
    authedPage: page,
  }) => {
    const unavailableAlbumId = "deleted-album";
    await page.addInitScript((albumId) => {
      localStorage.setItem("last-album-id", albumId);
    }, unavailableAlbumId);

    const staleRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes(`/albums/${unavailableAlbumId}`)) {
        staleRequests.push(request.url());
      }
    });

    await page.goto("/editor");
    await expect(page.getByRole("main").getByText("South America")).toBeVisible(
      {
        timeout: 15_000,
      },
    );
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("last-album-id")))
      .toBe("aid-1");
    expect(staleRequests).toEqual([]);
  });

  test("splits a chapter from the nav drawer", async ({ focusPage: page }) => {
    await page.goto("/editor");
    await expect(page.getByRole("main").getByText("South America")).toBeVisible(
      {
        timeout: 15_000,
      },
    );

    const nav = page.getByRole("navigation");
    await nav.getByRole("button", { name: "Chapter actions" }).first().click();
    await page.getByText("Split chapter").click();

    await expect(nav.getByText("Chapter 2")).toBeVisible();
  });
});

test.describe("responsive editor rails", () => {
  test("opens both rails on a wide desktop and toggles them independently", async ({
    authedPage: page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.goto("/editor");

    const navigation = page.locator("#editor-navigation");
    const inspector = page.locator("#editor-inspector");
    await expect(navigation).toBeVisible();
    await expect(inspector).toBeVisible();
    await expect(
      page.locator('.editor-header [aria-controls^="editor-"]'),
    ).toHaveCount(0);

    const hideNavigation = navigation.getByRole("button", {
      name: "Hide navigation",
    });
    await hideNavigation.focus();
    await hideNavigation.press("Enter");
    await expect(navigation).toBeHidden();
    await expect(inspector).toBeVisible();

    const showNavigation = page.locator(
      '.editor-rail-control--edge[aria-controls="editor-navigation"]',
    );
    await expect(showNavigation).toBeFocused();
    await showNavigation.press("Enter");
    await expect(navigation).toBeVisible();
    await expect(hideNavigation).toBeFocused();

    await inspector.getByRole("button", { name: "Hide inspector" }).click();
    await expect(inspector).toBeHidden();
    await expect(navigation).toBeVisible();
    await page
      .locator('.editor-rail-control--edge[aria-controls="editor-inspector"]')
      .click();
    await expect(inspector).toBeVisible();

    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(navigation).toBeVisible();
    await expect(inspector).toBeHidden();
  });

  test("attaches closed controls to their physical rails in RTL", async ({
    authedPage: page,
  }) => {
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ json: { ...mockUser, locale: "he" } }),
    );
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/editor");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const navigationBox = await page
      .locator('.editor-rail-control--edge[aria-controls="editor-navigation"]')
      .boundingBox();
    const inspectorBox = await page
      .locator('.editor-rail-control--edge[aria-controls="editor-inspector"]')
      .boundingBox();

    expect(navigationBox).not.toBeNull();
    expect(inspectorBox).not.toBeNull();
    expect(navigationBox!.x).toBeGreaterThan(900);
    expect(inspectorBox!.x).toBeLessThan(100);
  });
});
