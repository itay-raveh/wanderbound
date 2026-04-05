import { test as base, type Page } from "@playwright/test";
import {
  mockUser,
  mockAlbum,
  mockMedia,
  mockSteps,
  mockSegmentOutlines,
  mockFocusSteps,
  mockFocusMedia,
  TINY_JPEG_BASE64,
} from "../tests/fixtures/mocks";

const API = "**/api/v1";

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");

async function mockCommonApi(page: Page) {
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
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
    route.fulfill({ contentType: "image/jpeg", body: mediaBody }),
  );
}

async function mockDefaultSteps(page: Page) {
  await page.route(`${API}/albums/*/steps`, (route) =>
    route.fulfill({ json: mockSteps }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: mockMedia }),
  );
}

async function mockFocusData(page: Page) {
  // PATCH for step updates (sendToUnused, setAsCover) — accept optimistically.
  await page.route(`${API}/albums/*/steps/*`, (route) => {
    if (route.request().method() === "PATCH") {
      return route.fulfill({ json: {} });
    }
    return route.fallback();
  });
  await page.route(`${API}/albums/*/steps`, (route) =>
    route.fulfill({ json: mockFocusSteps }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: mockFocusMedia }),
  );
}

async function initPage(page: Page) {
  await page.addInitScript(() =>
    localStorage.setItem("last-album-id", "aid-1"),
  );
}

export const test = base.extend<{ authedPage: Page; focusPage: Page }>({
  authedPage: async ({ page }, use) => {
    await mockCommonApi(page);
    await mockDefaultSteps(page);
    await initPage(page);
    await use(page);
  },
  focusPage: async ({ page }, use) => {
    await mockCommonApi(page);
    await mockFocusData(page);
    await initPage(page);
    await use(page);
  },
});

export { expect } from "@playwright/test";
