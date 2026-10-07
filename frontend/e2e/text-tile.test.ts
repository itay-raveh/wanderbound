import { expect, openEditor, test } from "./fixtures";
import { mockAlbum, mockMedia, mockStep } from "../tests/fixtures/mocks";

test("editing and removing a text tile preserves photos and prints saved text", async ({
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
      const layout = route.request().postDataJSON();
      expect(layout.layout_version).toBe(1);
      step = { ...step, ...layout };
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
  await page.getByRole("button", { name: "Album page 1", exact: true }).click();
  await page.getByRole("button", { name: "Add text" }).click();

  await page
    .getByRole("button", { name: /Edit text tile:/ })
    .first()
    .click();
  const editor = page.getByRole("textbox", { name: "Text" });
  await expect(editor).toBeVisible();
  await editor.fill("Long text ".repeat(400));
  await expect(page.getByRole("alert")).toContainText("does not fit");
  await expect(editor).toHaveValue("");
  await editor.fill("A day in Lima");
  await editor.fill("Long text ".repeat(400));
  await expect(editor).toHaveValue("A day in Lima");
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

  const tile = page.getByRole("button", {
    name: "Edit text tile: A day in Lima",
  });
  await tile.focus();
  await tile.press("Enter");
  await expect(editor).toBeFocused();
  await editor.fill("Accepted text ".repeat(20));
  await expect(editor).toHaveValue("Accepted text ".repeat(20));
  await editor.fill("x\n".repeat(80));
  await expect(page.getByRole("alert")).toContainText("does not fit");
  await editor.press("Tab");
  await expect(editor).toBeVisible();
  expect(step.pages[0].slots.at(-1)?.text).toBe("A day in Lima");
  await editor.press("Escape");

  await page.getByRole("button", { name: "Remove text tile" }).click();
  const removeDialog = page.getByRole("dialog", {
    name: "Remove this text tile?",
  });
  await expect(removeDialog).toBeVisible();
  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  await removeDialog.getByRole("button", { name: "Cancel" }).click();
  await expect(removeDialog).toBeHidden();
  expect(step.pages[0].slots.at(-1)).toMatchObject({
    kind: "text",
    text: "A day in Lima",
  });

  await page.goto("/print/aid-1?part=content&chapter=chapter-1");
  await expect(page.locator(".page-content .text-item")).toContainText(
    "A day in Lima",
  );
  const pdf = await page.pdf({ printBackground: true });
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");

  await openEditor(page);
  await page.locator('[data-nav-step="1"]').click();
  await page.getByRole("button", { name: "Album page 1", exact: true }).click();
  await page.getByRole("button", { name: "Remove text tile" }).click();
  await removeDialog.getByRole("button", { name: "Remove text tile" }).click();
  await expect(page.locator(".page-content .text-item")).toHaveCount(0);
  expect(step.pages[0].slots.map((slot) => slot.id)).toEqual(originalSlots);
});
