import { test, expect } from "./fixtures";
import { MEDIA_UPGRADE_ONBOARDED_KEY } from "../src/utils/storage-keys";
import { mockUser, mockMedia } from "../tests/fixtures/mocks";
import type { Page } from "@playwright/test";

const API = "**/api/v1";

/** Build an SSE payload from an array of event objects. */
function sseBody(events: object[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

/** Mock user with Google Photos already connected. */
const connectedUser = {
  ...mockUser,
  google_photos_connected_at: "2026-01-01T00:00:00Z",
};

/** SSE match events: progress -> summary with 2 of 3 matched. */
const matchEvents = [
  { type: "matching", done: 1, total: 3 },
  { type: "matching", done: 2, total: 3 },
  { type: "matching", done: 3, total: 3 },
  {
    type: "match_summary",
    total_media: 3,
    matched: 2,
    unmatched: 1,
    matches: [
      { local_name: "photo1.jpg", google_id: "gid-1", step_id: 1 },
      { local_name: "photo2.jpg", google_id: "gid-2", step_id: 1 },
    ],
  },
];

/** SSE upgrade events: progress -> done with all replaced. */
const upgradeEvents = [
  { type: "downloading", done: 1, total: 2 },
  { type: "downloading", done: 2, total: 2 },
  { type: "done", replaced: 2, failed: 0 },
];

/** SSE upgrade events where one file fails. */
const upgradeEventsPartial = [
  { type: "downloading", done: 1, total: 2 },
  { type: "done", replaced: 1, failed: 1 },
];

async function setupUpgradeRoutes(page: Page) {
  // Override user route with connected user
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: connectedUser }),
  );

  // Picker session create
  await page.route(`${API}/google-photos/sessions`, (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        json: {
          session_id: "sess-1",
          picker_uri: "https://photos.google.com/picker/sess-1",
        },
      });
    }
    return route.fallback();
  });

  // Picker session poll - immediately ready
  await page.route(`${API}/google-photos/sessions/sess-1`, (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: { ready: true } });
    }
    // DELETE
    return route.fulfill({ status: 204, body: "" });
  });

  // Match SSE
  await page.route(`${API}/google-photos/match/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody(matchEvents),
    }),
  );
}

test.describe("Media Upgrade", () => {
  test("upgrade button visible for Google-linked user", async ({
    authedPage: page,
  }) => {
    // Default mockUser has google_sub set, so button should appear
    await page.goto("/editor");
    await expect(
      page.getByRole("button", { name: /upgrade/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("onboarding dialog shown on first upgrade", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    // Block window.open so Playwright doesn't try to open a real tab
    await page.addInitScript(() => {
      window.open = () => null;
    });
    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: /upgrade/i });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Onboarding dialog should appear since no localStorage key set
    await expect(page.getByText(/original quality/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("full upgrade flow: match -> confirm -> download -> done", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);

    // Skip onboarding
    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );

    // Block window.open
    await page.addInitScript(() => {
      window.open = () => null;
    });

    // Upgrade SSE
    await page.route(`${API}/google-photos/upgrade/**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody(upgradeEvents),
      }),
    );

    // Media invalidation after upgrade
    await page.route(`${API}/albums/*/media`, (route) =>
      route.fulfill({ json: mockMedia }),
    );

    await page.goto("/editor");

    // Click upgrade
    const upgradeBtn = page.getByRole("button", { name: /upgrade/i });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Match summary dialog should appear with "2 of 3" matched
    await expect(page.getByText(/2 of 3/)).toBeVisible({ timeout: 10_000 });

    // Confirm upgrade
    const confirmBtn = page.getByRole("button", {
      name: /replace with originals/i,
    });
    await expect(confirmBtn).toBeVisible();
    await confirmBtn.click();

    // Done state should show "Upgraded 2 files"
    await expect(page.getByText(/upgraded 2 files/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("partial failure shows count in done message", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);

    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );
    await page.addInitScript(() => {
      window.open = () => null;
    });

    // Upgrade SSE with partial failure
    await page.route(`${API}/google-photos/upgrade/**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody(upgradeEventsPartial),
      }),
    );

    await page.route(`${API}/albums/*/media`, (route) =>
      route.fulfill({ json: mockMedia }),
    );

    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: /upgrade/i });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Wait for match summary
    await expect(page.getByText(/2 of 3/)).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /replace with originals/i }).click();

    // Partial failure: "Upgraded 1 of 2 files"
    await expect(page.getByText(/upgraded 1 of 2/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("disconnect button visible when connected", async ({
    authedPage: page,
  }) => {
    // Override user to be connected
    await page.route(`${API}/users`, (route) =>
      route.fulfill({ json: connectedUser }),
    );

    await page.goto("/editor");

    await expect(
      page.getByRole("button", { name: /disconnect/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});
