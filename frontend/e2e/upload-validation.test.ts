import { expect, test } from "./fixtures";

test("rejected files leave the uploader ready for an accepted ZIP", async ({
  pendingSignupPage: page,
}) => {
  await page.route("**/api/v1/config", (route) =>
    route.fulfill({ json: { MAX_UPLOAD_SIZE_BYTES: 8 } }),
  );
  let uploads = 0;
  await page.route("**/api/v1/users/uploads/s3/**", (route) => {
    uploads += 1;
    return route.fulfill({ status: 503, json: { message: "Unavailable" } });
  });
  await page.goto("/upload");
  const input = page.locator('input[type="file"]');
  for (const [name, size, message] of [
    ["trip.txt", 1, "This file doesn't look like a valid Polarsteps export."],
    ["empty.zip", 0, "This file doesn't look like a valid Polarsteps export."],
    ["large.zip", 9, "File is too large."],
  ] as const) {
    await input.setInputFiles({
      name,
      mimeType: "application/zip",
      buffer: Buffer.alloc(size),
    });
    await expect(page.getByText(message, { exact: false })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /drop your file/i }),
    ).toBeVisible();
    expect(uploads).toBe(0);
  }
  const started = page.waitForRequest("**/api/v1/users/uploads/s3/**");
  await input.setInputFiles({
    name: "trip.ZIP",
    mimeType: "application/zip",
    buffer: Buffer.alloc(1),
  });
  await started;
  expect(uploads).toBe(1);
});
