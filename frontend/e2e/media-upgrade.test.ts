import type { Page } from "@playwright/test";

import { MEDIA_UPGRADE_ONBOARDED_KEY } from "../src/utils/storage-keys";
import { mockMedia, mockUser } from "../tests/fixtures/mocks";
import { sseBody } from "../tests/sse";
import {
  blockPopup,
  ensureExternalMediaOpen,
  expect,
  mockPopup,
  test,
} from "./fixtures";

const API = "**/api/v1";

const connectedUser = {
  ...mockUser,
  google_photos_connected_at: "2026-01-01T00:00:00Z",
};

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

const round2MatchEvents = [
  { type: "match_in_progress", phase: "matching", done: 1, total: 2 },
  { type: "match_in_progress", phase: "matching", done: 2, total: 2 },
  {
    type: "match_completed",
    total_picked: 2,
    matched: 1,
    already_upgraded: 0,
    unmatched: 1,
    matches: [{ local_name: "cover.jpg", google_id: "gid-3", distance: 0 }],
  },
];

const upgradeEvents = [
  { type: "download_in_progress", done: 1, total: 2 },
  { type: "download_in_progress", done: 2, total: 2 },
  { type: "upgrade_completed", replaced: 2, skipped: 0, failed: 0 },
];

const partialUpgradeEvents = [
  { type: "download_in_progress", done: 1, total: 2 },
  { type: "upgrade_completed", replaced: 1, skipped: 0, failed: 1 },
];

const threeFileUpgradeEvents = [
  { type: "download_in_progress", done: 1, total: 3 },
  { type: "download_in_progress", done: 2, total: 3 },
  { type: "download_in_progress", done: 3, total: 3 },
  { type: "upgrade_completed", replaced: 3, skipped: 0, failed: 0 },
];

function upgradeMediaButton(page: Page) {
  return page
    .locator(".media-panel")
    .getByRole("button", { name: "Upgrade Media" });
}

async function clickUpgradeMedia(page: Page) {
  await ensureExternalMediaOpen(page);
  const button = upgradeMediaButton(page);
  await expect(button).toBeVisible({ timeout: 15_000 });
  await button.scrollIntoViewIfNeeded();
  await button.click();
}

async function expectUpgradeDone(page: Page, message: RegExp) {
  await expect(page.locator(".media-panel .action-btn.done")).toHaveAttribute(
    "aria-label",
    message,
    { timeout: 10_000 },
  );
}

async function expectReadyFiles(page: Page, count: number) {
  await expect(
    page.getByText(new RegExp(`${count} files ready`, "i")),
  ).toBeVisible({ timeout: 10_000 });
}

async function skipOnboarding(page: Page) {
  await page.addInitScript(
    ([key]) => localStorage.setItem(key, "true"),
    [MEDIA_UPGRADE_ONBOARDED_KEY],
  );
}

async function mockConnectedUser(page: Page) {
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: connectedUser }),
  );
}

async function mockPickerSession(
  page: Page,
  {
    ready = true,
    sessionId = "sess-1",
    dynamicSession = false,
  }: { ready?: boolean; sessionId?: string; dynamicSession?: boolean } = {},
) {
  let count = 0;
  await page.route(`${API}/google-photos/sessions`, (route) => {
    if (route.request().method() !== "POST") {
      return route.fallback();
    }
    count += 1;
    const id = dynamicSession ? `sess-${count}` : sessionId;
    return route.fulfill({
      json: {
        session_id: id,
        picker_uri: `https://photos.google.com/picker/${id}`,
      },
    });
  });
  await page.route(
    `${API}/google-photos/sessions/${dynamicSession ? "sess-*" : sessionId}`,
    (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { ready } });
      }
      return route.fulfill({ status: 204, body: "" });
    },
  );
}

async function mockMatchStream(page: Page, events: object[] = matchEvents) {
  await page.route(`${API}/google-photos/match/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody(events),
    }),
  );
}

async function mockMatchRounds(page: Page, rounds: object[][]) {
  let round = 0;
  await page.route(`${API}/google-photos/match/**`, (route) => {
    const events = rounds[Math.min(round, rounds.length - 1)];
    round += 1;
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody(events),
    });
  });
}

async function mockUpgradeStream(page: Page, events: object[]) {
  await page.route(`${API}/google-photos/upgrade/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody(events),
    }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: mockMedia }),
  );
}

async function setupUpgradeRoutes(page: Page) {
  await mockConnectedUser(page);
  await mockPickerSession(page);
  await mockMatchStream(page);
}

async function openReadyUpgradeSummary(page: Page) {
  await page.goto("/editor");
  await clickUpgradeMedia(page);
  await expectReadyFiles(page, 2);
}

async function prepareOnboardedPopupFlow(page: Page) {
  await skipOnboarding(page);
  await mockPopup(page);
}

async function completeReadyUpgrade(
  page: Page,
  events: object[],
  expectedDone: RegExp,
) {
  await mockUpgradeStream(page, events);
  await openReadyUpgradeSummary(page);
  await page.getByRole("button", { name: /upgrade \d+ files/i }).click();
  await expectUpgradeDone(page, expectedDone);
}

test.describe("Media Upgrade", () => {
  test("upgrade button visible for Google-linked user", async ({
    editorPage: page,
  }) => {
    await ensureExternalMediaOpen(page);
    await expect(upgradeMediaButton(page)).toBeVisible({ timeout: 15_000 });
  });

  test("onboarding dialog shown on first upgrade", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    await page.goto("/editor");

    await clickUpgradeMedia(page);

    await expect(page.getByText(/original quality/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("full upgrade flow: match -> confirm -> download -> done", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await prepareOnboardedPopupFlow(page);
    await completeReadyUpgrade(page, upgradeEvents, /upgraded 2 files/i);
  });

  test("partial failure shows count in done message", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await prepareOnboardedPopupFlow(page);
    await completeReadyUpgrade(page, partialUpgradeEvents, /upgraded 1 of 2/i);
  });

  test("disconnect option visible in dropdown when connected", async ({
    authedPage: page,
  }) => {
    await mockConnectedUser(page);
    await page.goto("/editor");
    await ensureExternalMediaOpen(page);

    await page.getByRole("button", { name: "Upgrade options" }).click();

    await expect(page.getByRole("button", { name: /disconnect/i })).toBeVisible(
      { timeout: 5_000 },
    );
  });

  test("cancel from onboarding closes dialog and returns to idle", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    await page.goto("/editor");

    const upgradeBtn = upgradeMediaButton(page);
    await clickUpgradeMedia(page);
    await expect(page.getByText(/original quality/i)).toBeVisible({
      timeout: 5_000,
    });

    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/original quality/i)).not.toBeVisible();
  });

  test("cancel from match summary returns to idle", async ({
    authedPage: page,
  }) => {
    await setupUpgradeRoutes(page);
    await prepareOnboardedPopupFlow(page);
    await openReadyUpgradeSummary(page);

    const upgradeBtn = upgradeMediaButton(page);
    await page.getByRole("button", { name: "Cancel" }).click();

    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
  });

  test("cancel during picking aborts and returns to idle", async ({
    authedPage: page,
  }) => {
    await mockConnectedUser(page);
    await mockPickerSession(page, { ready: false });
    await prepareOnboardedPopupFlow(page);
    await page.goto("/editor");

    const upgradeBtn = upgradeMediaButton(page);
    await clickUpgradeMedia(page);
    const runningBtn = page
      .locator(".media-panel")
      .getByRole("button", { name: /waiting for selection/i });
    await expect(runningBtn).toBeVisible({ timeout: 5_000 });

    await runningBtn.scrollIntoViewIfNeeded();
    await runningBtn.click();

    await expect(upgradeBtn).toBeVisible({ timeout: 5_000 });
  });

  test("popup blocked surfaces error button", async ({ authedPage: page }) => {
    await setupUpgradeRoutes(page);
    await blockPopup(page);
    await skipOnboarding(page);
    await page.goto("/editor");

    await clickUpgradeMedia(page);

    const errorBtn = page.getByRole("button", {
      name: /upgrade failed\. try again/i,
    });
    await expect(errorBtn).toBeVisible({ timeout: 5_000 });
    await expect(errorBtn).toContainText(/allow popups and try again/i);
  });

  test("clicking error button restarts the flow", async ({
    authedPage: page,
  }) => {
    await mockConnectedUser(page);
    await mockPickerSession(page, { dynamicSession: true });
    await mockMatchRounds(page, [
      [{ type: "upgrade_failed", detail: "connectionLost" }],
      matchEvents,
    ]);
    await prepareOnboardedPopupFlow(page);
    await page.goto("/editor");

    await clickUpgradeMedia(page);
    const errorBtn = page.getByRole("button", {
      name: /upgrade failed\. try again/i,
    });
    await expect(errorBtn).toBeVisible({ timeout: 10_000 });
    await errorBtn.click();

    await expectReadyFiles(page, 2);
  });

  test("select more accumulates matches across rounds", async ({
    authedPage: page,
  }) => {
    await mockConnectedUser(page);
    await mockPickerSession(page, { dynamicSession: true });
    await mockMatchRounds(page, [matchEvents, round2MatchEvents]);
    await mockUpgradeStream(page, threeFileUpgradeEvents);
    await prepareOnboardedPopupFlow(page);
    await openReadyUpgradeSummary(page);

    await page.getByRole("button", { name: /select more/i }).click();
    await expectReadyFiles(page, 3);
    await page.getByRole("button", { name: /upgrade 3 files/i }).click();

    await expectUpgradeDone(page, /upgraded 3 files/i);
  });
});
