import { test as base, type Page } from "@playwright/test";
import {
  mockUser,
  mockAlbum,
  mockMedia,
  mockSteps,
  mockSegmentOutlines,
  TINY_JPEG_BASE64,
} from "../tests/fixtures/mocks";

const API = "**/api/v1";

async function mockAllApi(page: Page) {
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route(`${API}/albums/*/steps`, (route) =>
    route.fulfill({ json: mockSteps }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: mockMedia }),
  );
  await page.route(`${API}/albums/*/segments`, (route) =>
    route.fulfill({ json: mockSegmentOutlines }),
  );
  await page.route(`${API}/albums/*`, (route) =>
    route.fulfill({ json: mockAlbum }),
  );
  await page.route(`${API}/auth/google`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route("**/media/**", (route) =>
    route.fulfill({
      contentType: "image/jpeg",
      body: Buffer.from(TINY_JPEG_BASE64, "base64"),
    }),
  );
}

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    await mockAllApi(page);
    await page.addInitScript(() =>
      localStorage.setItem("last-album-id", "aid-1"),
    );
    await use(page);
  },
});

export { expect } from "@playwright/test";
