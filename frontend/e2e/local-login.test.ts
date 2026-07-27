import { expect, test } from "./fixtures";

const API = "**/api/v1";

test("a Polarsteps ZIP establishes the local browser session", async ({ page }) => {
  const localUser = {
    id: 999,
    google_sub: null,
    microsoft_sub: null,
    first_name: "Zip",
    profile_image_url: null,
    locale: "en-US",
    unit_is_km: true,
    temperature_is_celsius: true,
    living_location: null,
    album_ids: ["trip-1"],
    is_demo: false,
    has_data: true,
    is_processed: false,
    google_photos_connected_at: null,
  };
  const uploadResult = {
    user: localUser,
    trips: [
      {
        id: "trip-1",
        title: "Test Trip",
        step_count: 1,
        country_codes: ["nl"],
      },
    ],
  };
  let authenticated = false;

  await page.route(`${API}/config`, (route) =>
    route.fulfill({
      json: {
        GOOGLE_CLIENT_ID: "",
        MICROSOFT_CLIENT_ID: "",
        MAX_UPLOAD_SIZE_BYTES: 1024 ** 3,
      },
    }),
  );
  await page.route(`${API}/auth/state`, (route) =>
    route.fulfill({
      json: authenticated
        ? { state: "authenticated", user: localUser }
        : { state: "anonymous", user: null },
    }),
  );
  await page.route(`${API}/users`, (route) =>
    authenticated
      ? route.fulfill({ json: localUser })
      : route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
  await page.route(`${API}/users/uploads/pending`, (route) =>
    route.fulfill({ contentType: "application/json", body: "null" }),
  );
  await page.route(`${API}/users/uploads/s3/multipart`, (route) =>
    route.fulfill({
      status: 201,
      json: { uploadId: "local-upload", key: "uploads/local-upload.zip" },
    }),
  );
  await page.route(
    `${API}/users/uploads/s3/multipart/local-upload/1*`,
    (route) =>
      route.fulfill({
        json: {
          method: "PUT",
          url: "http://localhost:5173/local-upload-part",
          headers: {},
        },
      }),
  );
  await page.route("**/local-upload-part", (route) =>
    route.fulfill({ status: 200, headers: { ETag: '"etag"' } }),
  );
  await page.route(
    `${API}/users/uploads/s3/multipart/local-upload/complete*`,
    (route) =>
      route.fulfill({ json: { location: "uploads/local-upload.zip" } }),
  );
  await page.route(`${API}/users/uploads/local-upload/stream`, (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: 'data: {"type":"complete"}\n\n',
    }),
  );
  await page.route(`${API}/users/uploads/local-upload/complete`, (route) => {
    authenticated = true;
    return route.fulfill({ json: uploadResult });
  });
  await page.route(`${API}/users/process`, (route) =>
    route.fulfill({ contentType: "text/event-stream", body: "" }),
  );

  await page.goto("/");
  await page.getByRole("link", { name: "Log in with Polarsteps ZIP" }).click();
  await page.waitForURL("/upload");
  await page.locator('input[type="file"]').setInputFiles({
    name: "user_data.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("valid-test-archive"),
  });

  await expect(page.getByText("Your album is ready")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Zip")).toBeVisible();
});

test("provider mode keeps anonymous upload behind sign in", async ({ page }) => {
  await page.route(`${API}/config`, (route) =>
    route.fulfill({
      json: {
        GOOGLE_CLIENT_ID: "configured",
        MICROSOFT_CLIENT_ID: "",
        MAX_UPLOAD_SIZE_BYTES: 1024 ** 3,
      },
    }),
  );
  await page.route(`${API}/auth/state`, (route) =>
    route.fulfill({ json: { state: "anonymous", user: null } }),
  );

  await page.goto("/upload");

  await page.waitForURL("/");
  await expect(page.getByRole("heading", { name: "Wanderbound" })).toBeVisible();
});
