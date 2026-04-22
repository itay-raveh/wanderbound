import { test, expect, mockPopup, blockPopup } from "./fixtures";
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
  { type: "match_in_progress", phase: "matching", done: 1, total: 3 },
  { type: "match_in_progress", phase: "matching", done: 2, total: 3 },
  { type: "match_in_progress", phase: "matching", done: 3, total: 3 },
  {
    type: "match_completed",
    total_picked: 3,
    matched: 2,
    already_upgraded: 0,
    unmatched: 1,
    matches: [
      { local_name: "photo1.jpg", google_id: "gid-1", distance: 0 },
      { local_name: "photo2.jpg", google_id: "gid-2", distance: 0 },
    ],
  },
];

/** SSE upgrade events: progress -> completed with all replaced. */
const upgradeEvents = [
  { type: "download_in_progress", done: 1, total: 2 },
  { type: "download_in_progress", done: 2, total: 2 },
  { type: "upgrade_completed", replaced: 2, skipped: 0, failed: 0 },
];

/** SSE upgrade events where one file fails. */
const upgradeEventsPartial = [
  { type: "download_in_progress", done: 1, total: 2 },
  { type: "upgrade_completed", replaced: 1, skipped: 0, failed: 1 },
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
      page.getByRole("button", { name: "Upgrade Media" }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("onboarding dialog shown on first upgrade", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
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

    await mockPopup(page);

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
    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Match summary dialog should appear
    await expect(page.getByText(/2 files ready/i)).toBeVisible({ timeout: 10_000 });

    // Confirm upgrade
    const confirmBtn = page.getByRole("button", {
      name: /upgrade \d+ files/i,
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
    await mockPopup(page);

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

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Wait for match summary
    await expect(page.getByText(/2 files ready/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /upgrade \d+ files/i }).click();

    // Partial failure: "Upgraded 1 of 2 files"
    await expect(page.getByText(/upgraded 1 of 2/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("disconnect option visible in dropdown when connected", async ({
    authedPage: page,
  }) => {
    // Override user to be connected
    await page.route(`${API}/users`, (route) =>
      route.fulfill({ json: connectedUser }),
    );

    await page.goto("/editor");

    // Split-trigger chevron opens the dropdown menu
    const splitTrigger = page.getByRole("button", {
      name: "Upgrade options",
    });
    await expect(splitTrigger).toBeVisible({ timeout: 15_000 });
    await splitTrigger.click();

    // Disconnect option should appear in the dropdown
    await expect(
      page.getByRole("button", { name: /disconnect/i }),
    ).toBeVisible({ timeout: 5_000 });
  });

  // -- Cancel flows ----------------------------------------------------------

  test("cancel from onboarding closes dialog and returns to idle", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Onboarding dialog should appear
    await expect(page.getByText(/original quality/i)).toBeVisible({
      timeout: 5_000,
    });

    // Cancel - computed setter triggers upgrade.cancel()
    await page.getByRole("button", { name: "Cancel" }).click();

    // Should return to idle
    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/original quality/i)).not.toBeVisible();
  });

  test("cancel from match summary returns to idle", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );
    await mockPopup(page);

    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Match summary with "2 files ready"
    await expect(page.getByText(/2 files ready/i)).toBeVisible({
      timeout: 10_000,
    });

    // Cancel - computed setter triggers upgrade.cancel()
    await page.getByRole("button", { name: "Cancel" }).click();

    // Should return to idle
    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
  });

  test("cancel during picking aborts and returns to idle", async ({
    authedPage: page,
  }) => {
    await page.route(`${API}/users`, (route) =>
      route.fulfill({ json: connectedUser }),
    );
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
    // Poll always returns not-ready so picking phase persists
    await page.route(`${API}/google-photos/sessions/sess-1`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { ready: false } });
      }
      return route.fulfill({ status: 204, body: "" });
    });

    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );
    await mockPopup(page);

    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Should enter picking phase with running button
    const runningBtn = page.getByRole("button", {
      name: /waiting for selection/i,
    });
    await expect(runningBtn).toBeVisible({ timeout: 5_000 });

    // Click running button to cancel
    await runningBtn.click();

    // Should return to idle
    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
  });

  // -- Error paths -----------------------------------------------------------

  test("popup blocked surfaces error button", async ({ authedPage: page }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    // Skip onboarding so the start() path opens the popup directly
    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );

    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Error state button appears with translated popup-blocked copy inside
    const errorBtn = page.getByRole("button", {
      name: /upgrade failed\. try again/i,
    });
    await expect(errorBtn).toBeVisible({ timeout: 5_000 });
    await expect(errorBtn).toContainText(/allow popups and try again/i);
  });

  test("clicking error button restarts the flow", async ({
    authedPage: page,
  }) => {
    // First match request returns an SSE error; second returns real matches.
    let matchCall = 0;
    await page.route(`${API}/users`, (route) =>
      route.fulfill({ json: connectedUser }),
    );
    await page.route(`${API}/google-photos/sessions`, (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          json: {
            session_id: `sess-${matchCall + 1}`,
            picker_uri: `https://photos.google.com/picker/sess-${matchCall + 1}`,
          },
        });
      }
      return route.fallback();
    });
    await page.route(`${API}/google-photos/sessions/sess-*`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { ready: true } });
      }
      return route.fulfill({ status: 204, body: "" });
    });
    await page.route(`${API}/google-photos/match/**`, (route) => {
      matchCall++;
      if (matchCall === 1) {
        return route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: sseBody([{ type: "upgrade_failed", detail: "connectionLost" }]),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody(matchEvents),
      });
    });

    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );
    await mockPopup(page);
    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    const errorBtn = page.getByRole("button", {
      name: /upgrade failed\. try again/i,
    });
    await expect(errorBtn).toBeVisible({ timeout: 10_000 });
    await errorBtn.click();

    // Second attempt reaches match summary
    await expect(page.getByText(/2 files ready/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  // -- Select more flow ------------------------------------------------------

  test("select more accumulates matches across rounds", async ({
    authedPage: page,
  }) => {
    let sessionCount = 0;

    await page.route(`${API}/users`, (route) =>
      route.fulfill({ json: connectedUser }),
    );
    await page.route(`${API}/google-photos/sessions`, (route) => {
      if (route.request().method() === "POST") {
        sessionCount++;
        return route.fulfill({
          json: {
            session_id: `sess-${sessionCount}`,
            picker_uri: `https://photos.google.com/picker/sess-${sessionCount}`,
          },
        });
      }
      return route.fallback();
    });
    // Both sessions immediately ready; DELETE returns 204
    await page.route(`${API}/google-photos/sessions/sess-*`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { ready: true } });
      }
      return route.fulfill({ status: 204, body: "" });
    });

    const round2MatchEvents = [
      { type: "match_in_progress", phase: "matching", done: 1, total: 2 },
      { type: "match_in_progress", phase: "matching", done: 2, total: 2 },
      {
        type: "match_completed",
        total_picked: 2,
        matched: 1,
        already_upgraded: 0,
        unmatched: 1,
        matches: [
          { local_name: "cover.jpg", google_id: "gid-3", distance: 0 },
        ],
      },
    ];

    let matchRound = 0;
    await page.route(`${API}/google-photos/match/**`, (route) => {
      matchRound++;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody(matchRound === 1 ? matchEvents : round2MatchEvents),
      });
    });

    await page.route(`${API}/google-photos/upgrade/**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          { type: "download_in_progress", done: 1, total: 3 },
          { type: "download_in_progress", done: 2, total: 3 },
          { type: "download_in_progress", done: 3, total: 3 },
          { type: "upgrade_completed", replaced: 3, skipped: 0, failed: 0 },
        ]),
      }),
    );

    await page.route(`${API}/albums/*/media`, (route) =>
      route.fulfill({ json: mockMedia }),
    );

    await page.addInitScript(
      ([key]) => localStorage.setItem(key, "1"),
      [MEDIA_UPGRADE_ONBOARDED_KEY],
    );
    await mockPopup(page);

    await page.goto("/editor");

    const upgradeBtn = page.getByRole("button", { name: "Upgrade Media" });
    await expect(upgradeBtn).toBeVisible({ timeout: 15_000 });
    await upgradeBtn.click();

    // Round 1: summary shows "2 files ready to upgrade"
    await expect(page.getByText(/2 files ready/i)).toBeVisible({
      timeout: 10_000,
    });

    // Click "Select More" to start round 2
    await page.getByRole("button", { name: /select more/i }).click();

    // After round 2, merged summary shows "3 files ready to upgrade"
    await expect(page.getByText(/3 files ready/i)).toBeVisible({
      timeout: 10_000,
    });

    // Confirm upgrade
    await page.getByRole("button", { name: /upgrade 3 files/i }).click();

    // Done
    await expect(page.getByText(/upgraded 3 files/i)).toBeVisible({
      timeout: 10_000,
    });
  });
});
