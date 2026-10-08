import { test, expect } from "./fixtures";
import { mockAlbum, mockFocusSteps, mockUser } from "../tests/fixtures/mocks";

test.describe("Editor", () => {
  test("recovers one missing map without replacing a customized map", async ({
    focusPage: page,
  }) => {
    let album = {
      ...mockAlbum,
      chapters: [
        { ...mockAlbum.chapters[0], step_ids: mockFocusSteps.map((s) => s.id) },
      ],
      maps_ranges: [["2024-01-03", "2024-01-03"]],
    };
    await page.route("**/api/v1/albums/aid-1", (route) => {
      if (route.request().method() === "PATCH") {
        album = { ...album, ...route.request().postDataJSON() };
      }
      return route.fulfill({ json: album });
    });
    await page.goto("/editor");
    const nav = page.getByRole("navigation");
    await expect(nav.getByRole("button", { name: /^Map:/ })).toHaveCount(1, {
      timeout: 15000,
    });
    await nav.getByRole("button", { name: "Add map", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Ending step").click();
    await page.getByRole("option").filter({ hasText: "Buenos Aires" }).click();
    await dialog.getByRole("button", { name: "Add map", exact: true }).click();
    await expect
      .poll(() => album.maps_ranges)
      .toEqual([
        ["2024-01-03", "2024-01-03"],
        ["2024-01-01", "2024-01-01"],
      ]);
    await page.reload();
    await expect(nav.getByRole("button", { name: /^Map:/ })).toHaveCount(2, {
      timeout: 15000,
    });
  });
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
  test("keeps both rails and the scrolled album usable at the smallest editor width", async ({
    focusPage: page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/editor");
    await page.locator('[data-nav-step="103"]').click();
    const step = page
      .locator(".album-container .step-main")
      .filter({ hasText: "Santiago" });
    await expect(step).toBeInViewport();
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(2000);
    const position = page.locator(".page-position");
    const label = await position.innerText();

    await expect(page.locator("#editor-navigation")).toBeVisible();
    await expect(page.locator("#editor-inspector")).toBeVisible();
    await expect(page.locator("body")).not.toHaveClass(
      /q-body--prevent-scroll/,
    );
    await expect(page.getByRole("button", { name: "Add text" })).toBeVisible();
    await page
      .getByRole("button", { name: 'Collapse "Photos and text"' })
      .click();
    await expect(page.getByRole("button", { name: "Add text" })).toBeHidden();
    await expect(page.getByRole("region", { name: "Unused" })).toBeHidden();
    await page
      .getByRole("button", { name: 'Expand "Photos and text"' })
      .click();
    await expect(page.locator(".album-container")).toBeInViewport();

    await expect(step).toBeInViewport();
    const navigationBox = await page
      .locator("#editor-navigation")
      .boundingBox();
    const inspectorBox = await page.locator("#editor-inspector").boundingBox();
    const pageBox = await step.boundingBox();
    expect(pageBox!.x).toBeGreaterThanOrEqual(
      navigationBox!.x + navigationBox!.width,
    );
    expect(pageBox!.x + pageBox!.width).toBeLessThanOrEqual(inspectorBox!.x);
    await expect(position).toHaveText(label);
    await page.getByRole("button", { name: "Hide inspector" }).click();
    await expect(page.locator("#editor-inspector")).toBeHidden();
    await expect(page.locator("body")).not.toHaveClass(
      /q-body--prevent-scroll/,
    );
    await expect(step).toBeInViewport();
    await expect(position).toHaveText(label);
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(2000);
    const restoredScrollY = await page.evaluate(() => window.scrollY);
    await page.mouse.move(512, 384);
    await page.mouse.wheel(0, -600);
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeLessThan(restoredScrollY);
    await page.getByRole("button", { name: "Show inspector" }).click();
    await expect(page.locator("#editor-inspector")).toBeVisible();
  });

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
    await expect(inspector).toBeVisible();
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
    await page
      .locator('#editor-navigation button[aria-controls="editor-navigation"]')
      .click();
    await page
      .locator('#editor-inspector button[aria-controls="editor-inspector"]')
      .click();

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
