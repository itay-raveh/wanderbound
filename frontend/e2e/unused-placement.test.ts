import { expect, openEditor, scrollToStep, test } from "./fixtures";
import { mockComposedPage, mockStep } from "../tests/fixtures/mocks";
import type { StepMediaLayoutUpdate } from "../src/client";

test("unused photo can be placed on a page with the keyboard", async ({
  authedPage: page,
}) => {
  const original: StepMediaLayoutUpdate = {
    layout_version: 1,
    cover: null,
    pages: [mockComposedPage("grid", ["photo1.jpg"])],
    unused: ["photo2.jpg"],
  };
  let step = { ...mockStep, ...original };
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [step] }),
  );
  await page.route("**/api/v1/albums/aid-1/steps/1/media-layout", (route) => {
    const layout: StepMediaLayoutUpdate = route.request().postDataJSON();
    step = { ...step, ...layout };
    return route.fulfill({ json: step });
  });

  await openEditor(page);
  await scrollToStep(page, "Amsterdam");
  const place = page.getByRole("button", {
    name: "Place photo2.jpg on a page",
  });
  await place.focus();
  await page.keyboard.press("Enter");
  const target = page.getByRole("menuitem", { name: "Album page 1" });
  await expect(target).toBeVisible();
  await target.focus();
  await page.keyboard.press("Enter");

  await expect
    .poll(() => step.pages[0]?.media)
    .toEqual(["photo1.jpg", "photo2.jpg"]);
  expect(step.unused).toEqual([]);
  await expect(place).toHaveCount(0);
  await expect(page.locator(".unused-drawer .drawer-header")).toBeFocused();
});

test("photo can be dragged into the open inspector tray at 1024px", async ({
  authedPage: page,
}) => {
  let step = {
    ...mockStep,
    cover: null,
    pages: [mockComposedPage("grid", ["photo1.jpg", "photo2.jpg"])],
    unused: [] as string[],
  };
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [step] }),
  );
  await page.route("**/api/v1/albums/aid-1/steps/1/media-layout", (route) => {
    const layout: StepMediaLayoutUpdate = route.request().postDataJSON();
    step = { ...step, ...layout };
    return route.fulfill({ json: step });
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await openEditor(page);
  await scrollToStep(page, "Amsterdam");
  await page.getByRole("button", { name: "Album page 1", exact: true }).click();
  await expect(page.locator("#editor-navigation")).toBeVisible();
  await expect(page.locator("#editor-inspector")).toBeVisible();
  await page
    .locator('.page-content .media-item[data-media="photo2.jpg"]')
    .dragTo(page.locator(".unused-drawer .drawer-track"));

  await expect.poll(() => step.unused).toEqual(["photo2.jpg"]);
  await expect(
    page.locator('.unused-drawer .media-item[data-media="photo2.jpg"]'),
  ).toBeVisible();
});
