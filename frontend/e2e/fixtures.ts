import { test as base, type Page } from "@playwright/test";
import {
  mockUser,
  mockAuthStateAuthenticated,
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

// Strict mock guard: register first so it matches last (Playwright is LIFO).
// Any /api/v1/** request not handled by a later, more specific route lands
// here and is recorded. Tests fail in teardown if anything was recorded  -
// preventing silent fall-through to the dev-server proxy and a non-existent
// backend, which would otherwise mask missing mocks behind passing tests.
async function installStrictMockGuard(page: Page) {
  const unmocked: string[] = [];
  await page.route(`${API}/**`, (route) => {
    unmocked.push(route.request().url());
    return route.abort();
  });
  return () => {
    if (unmocked.length) {
      throw new Error(
        `Unmocked API calls detected in test:\n  ${unmocked.join("\n  ")}`,
      );
    }
  };
}

async function mockCommonApi(page: Page) {
  await page.route(`${API}/auth/state`, (route) =>
    route.fulfill({ json: mockAuthStateAuthenticated }),
  );
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route(`${API}/albums/*/segments`, (route) =>
    route.fulfill({ json: mockSegmentOutlines }),
  );
  await page.route(`${API}/albums/*/segments/points*`, (route) =>
    route.fulfill({ json: [] }),
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
  // PATCH for step updates (sendToUnused, setAsCover) - accept optimistically.
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

export async function mockPopup(page: Page) {
  await page.addInitScript(() => {
    window.open = () =>
      ({
        closed: false,
        close() {
          this.closed = true;
        },
        location: { href: "" },
        document: {
          title: "",
          body: { style: { cssText: "" }, textContent: "" },
        },
      }) as unknown as Window;
  });
}

export async function blockPopup(page: Page) {
  await page.addInitScript(() => {
    window.open = () => null;
  });
}

export const test = base.extend<{ authedPage: Page; focusPage: Page }>({
  page: async ({ page }, use) => {
    const assertAllMocked = await installStrictMockGuard(page);
    await use(page);
    assertAllMocked();
  },
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
