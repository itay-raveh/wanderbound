import { expect, openEditor, scrollToStep, test } from "./fixtures";
import { mockMedia, mockStep } from "../tests/fixtures/mocks";

const source = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100" viewBox="0 0 160 100"><rect width="160" height="100" fill="#2972aa"/><circle cx="100" cy="50" r="25" fill="#ffce54"/></svg>`;

test("edits a photo globally with full rotation and keyboard crop controls", async ({
  authedPage: page,
}) => {
  let savedEdit: Record<string, number> | null = null;
  let media = mockMedia.map((item) => ({
    ...item,
    aid: "aid-1",
    uid: 1,
    kind: "photo",
    panorama_candidate: false,
    photo_edit: null as Record<string, number> | null,
    updated_at: "2026-09-29T00:00:00Z",
  }));
  await page.route("**/api/v1/albums/aid-1/media", (route) =>
    route.fulfill({ json: media }),
  );
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [{ ...mockStep, unused: ["photo2.jpg"] }] }),
  );
  await page.route("**/api/v1/albums/aid-1/media/*.jpg*", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: source }),
  );
  await page.route("**/api/v1/albums/aid-1/media/photo1.jpg/photo-source*", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: source }),
  );
  await page.route("**/api/v1/albums/aid-1/media/photo1.jpg/photo-edit", (route) => {
    savedEdit = route.request().postDataJSON() as Record<string, number>;
    media = media.map((item) =>
      item.name === "photo1.jpg"
        ? { ...item, photo_edit: savedEdit, updated_at: "2026-09-29T00:01:00Z" }
        : item,
    );
    return route.fulfill({ json: media.find((item) => item.name === "photo1.jpg") });
  });
  await openEditor(page);
  await scrollToStep(page, "Amsterdam");
  await page.locator('[data-media="photo1.jpg"] .album-action').first().click();
  const dialog = page.getByRole("dialog", { name: "Edit photo" });
  await expect(dialog).toBeVisible();
  const range = dialog.getByRole("slider", { name: "Rotation" });
  await expect(range).toHaveAttribute("min", "-180");
  await expect(range).toHaveAttribute("max", "180");
  await expect(dialog.locator(".crop-box")).toBeVisible();

  await dialog.getByRole("spinbutton", { name: "Rotation angle in degrees" }).fill("90");
  await dialog.getByRole("spinbutton", { name: "Rotation angle in degrees" }).blur();
  await expect(dialog.getByRole("spinbutton", { name: "Rotation angle in degrees" })).toHaveValue("90.0");
  await dialog.getByRole("slider", { name: "Zoom" }).fill("2");
  const crop = dialog.locator(".crop-box");
  const before = await crop.evaluate((element) => element.style.left);
  await crop.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => crop.evaluate((element) => element.style.left)).not.toBe(before);
  await dialog.getByRole("button", { name: "Apply changes" }).click();
  await expect(dialog).toBeHidden();
  expect(savedEdit?.angle).toBe(90);

  await page
    .locator('#editor-inspector [data-media="photo2.jpg"] button[aria-label="Edit photo"]')
    .click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "Print preview", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Print preview" });
  await preview.getByRole("button", { name: "Next spread" }).click();
  await preview.getByRole("button", { name: "Next spread" }).click();
  await expect(preview.locator('img[src*="photo1.jpg"]')).toHaveCount(1);
  await expect(preview.getByRole("button", { name: "Edit photo" })).toHaveCount(0);
});
