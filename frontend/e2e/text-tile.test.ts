import { expect, openEditor, test } from "./fixtures";
import { mockAlbum, mockMedia, mockStep } from "../tests/fixtures/mocks";

test("adding and editing text preserves photos and prints the saved tile", async ({
  authedPage: page,
}) => {
  let step = { ...mockStep, aid: "aid-1", uid: 1 };
  const originalSlots = step.pages[0].slots.map((slot) => slot.id);
  await page.route("**/api/v1/albums/aid-1", (route) =>
    route.fulfill({ json: mockAlbum }),
  );
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [step] }),
  );
  await page.route("**/api/v1/albums/aid-1/media", (route) =>
    route.fulfill({ json: mockMedia }),
  );
  await page.route(
    "**/api/v1/albums/aid-1/steps/1/media-layout",
    async (route) => {
      step = { ...step, ...route.request().postDataJSON() };
      await route.fulfill({ json: step });
    },
  );
  await page.route("**/api/v1/albums/aid-1/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: mockAlbum,
        steps: [step],
        segments: [],
        total_distance_km: 0,
      },
    }),
  );

  await openEditor(page);
  await page.locator('[data-nav-step="1"]').click();
  await page.getByRole("button", { name: "Actions for album page 1" }).click();
  await page.getByRole("menuitem", { name: "Add text tile" }).click();

  await page.getByRole("button", { name: "Edit text tile" }).first().click();
  const editor = page.getByRole("textbox", { name: "Text" });
  await expect(editor).toBeVisible();
  await editor.fill("Long text ".repeat(400));
  await expect(page.getByRole("alert")).toContainText("does not fit");
  await expect(editor).toHaveValue("");
  await editor.fill("A day in Lima");
  await editor.press("Tab");

  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  expect(step.pages[0].slots.map((slot) => slot.id)).toEqual([
    ...originalSlots,
    expect.any(String),
  ]);
  expect(step.pages[0].slots.at(-1)).toMatchObject({
    kind: "text",
    text: "A day in Lima",
  });
  expect(step.unused).toEqual([]);

  await page.goto("/print/aid-1?part=content&chapter=chapter-1");
  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  const pdf = await page.pdf({ printBackground: true });
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
});
