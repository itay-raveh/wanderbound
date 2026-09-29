import { expect, openEditor, test } from "./fixtures";
import { mockAlbum, mockMedia, mockStep } from "../tests/fixtures/mocks";

test("replacing a photo with text keeps its slot and prints the same text", async ({
  authedPage: page,
}) => {
  let step = { ...mockStep, aid: "aid-1", uid: 1 };
  const originalSlot = step.pages[0].slots[1].id;
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
  await page.getByRole("button", { name: "Replace photo with text" }).click();
  await page
    .getByRole("textbox", { name: "Text" })
    .fill("Long text ".repeat(400));
  await expect(page.getByRole("button", { name: "Save text" })).toBeDisabled();
  await page.getByRole("textbox", { name: "Text" }).fill("A day in Lima");
  await page.getByRole("button", { name: "Save text" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  expect(step.pages[0].slots[1].id).toBe(originalSlot);
  expect(step.pages[0].slots[1].kind).toBe("text");
  expect(step.unused).toContain("photo2.jpg");

  await page
    .locator('.unused-drawer [data-media="photo2.jpg"]')
    .dragTo(page.locator(".page-content .text-item"));
  await expect.poll(() => step.unused).toEqual([]);
  expect(
    step.pages[0].slots.some(
      (slot) => slot.id === originalSlot && slot.kind === "text",
    ),
  ).toBe(true);

  await page.goto("/print/aid-1?part=content&chapter=chapter-1");
  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  const pdf = await page.pdf({ printBackground: true });
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
});
