import { expect, test, type Page } from "@playwright/test";
import { TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const API = "**/api/v1";
const STEP_COUNT = 240;
const PHOTOS_PER_STEP = 4;

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");

function photoName(stepIndex: number, photoIndex: number) {
  return `large-step-${stepIndex}-photo-${photoIndex}.jpg`;
}

function makeLargeMedia() {
  const media = [
    { name: "cover.jpg", width: 1920, height: 1080 },
    { name: "back.jpg", width: 1920, height: 1080 },
  ];
  for (let step = 1; step <= STEP_COUNT; step++) {
    for (let photo = 1; photo <= PHOTOS_PER_STEP; photo++) {
      media.push({
        name: photoName(step, photo),
        width: photo % 2 === 0 ? 1080 : 1920,
        height: photo % 2 === 0 ? 1920 : 1080,
      });
    }
  }
  return media;
}

function makeLargeSteps() {
  return Array.from({ length: STEP_COUNT }, (_, index) => {
    const stepNumber = index + 1;
    const photos = Array.from({ length: PHOTOS_PER_STEP }, (_, photoIndex) =>
      photoName(stepNumber, photoIndex + 1),
    );
    const timestamp = 1_704_067_200 + index * 86_400;
    return {
      id: stepNumber,
      name: `Large Step ${stepNumber}`,
      description: `Large album stop ${stepNumber}.`,
      timestamp,
      timezone_id: "Europe/Amsterdam",
      location: {
        name: `Place ${stepNumber}`,
        detail: "Large route",
        country_code: "nl",
        lat: 52 + index * 0.001,
        lon: 4 + index * 0.001,
      },
      elevation: 0,
      weather: {
        day: { temp: 20, feels_like: 18, icon: "clear-day" },
        night: null,
      },
      cover: photos[0],
      pages: [photos],
      unused: [],
      datetime: new Date(timestamp * 1000).toISOString(),
    };
  });
}

async function mockLargeAlbum(page: Page) {
  const steps = makeLargeSteps();
  const media = makeLargeMedia();
  await page.addInitScript(() =>
    localStorage.setItem("last-album-id", "large-album"),
  );
  await page.route(`${API}/auth/state`, (route) =>
    route.fulfill({
      json: {
        state: "authenticated",
        user: {
          id: 1,
          first_name: "Test",
          last_name: "User",
          google_sub: "g-1",
          profile_image_url: null,
          locale: "en-US",
          unit_is_km: true,
          temperature_is_celsius: true,
          album_ids: ["large-album"],
          has_data: true,
          is_processed: true,
          living_location: null,
        },
        pending_first_name: null,
        pending_picture: null,
      },
    }),
  );
  await page.route(`${API}/users`, (route) =>
    route.fulfill({
      json: {
        id: 1,
        first_name: "Test",
        last_name: "User",
        google_sub: "g-1",
        profile_image_url: null,
        locale: "en-US",
        unit_is_km: true,
        temperature_is_celsius: true,
        album_ids: ["large-album"],
        has_data: true,
        is_processed: true,
        living_location: null,
      },
    }),
  );
  await page.route(`${API}/albums/*`, (route) =>
    route.fulfill({
      json: {
        id: "large-album",
        uid: 1,
        title: "Large Album",
        subtitle: "Performance fixture",
        hidden_steps: [],
        hidden_headers: [],
        maps_ranges: [],
        safe_margin_mm: 0,
        front_cover_photo: "cover.jpg",
        back_cover_photo: "back.jpg",
        colors: { nl: "#e77c31", be: "#3d7a5f", de: "#496b94" },
      },
    }),
  );
  await page.route(`${API}/albums/*/segments`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`${API}/albums/*/segments/points*`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`${API}/albums/*/steps`, (route) =>
    route.fulfill({ json: steps }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: media }),
  );
  await page.route("**/media/**", (route) =>
    route.fulfill({ contentType: "image/jpeg", body: mediaBody }),
  );
}

async function scrollNavStepIntoView(page: Page, step: number) {
  const navList = page.locator(".group-entries-virtual");
  const target = page.locator(`[data-nav-step="${step}"]`);
  for (let scrollTop = 0; scrollTop <= 14_000; scrollTop += 700) {
    await navList.evaluate((el, top) => {
      el.scrollTop = top;
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    }, scrollTop);
    await page.waitForTimeout(50);
    if ((await target.count()) > 0) {
      await expect(target).toBeVisible({ timeout: 1_000 });
      return;
    }
  }
  await expect(target).toBeVisible({ timeout: 1_000 });
}

async function activeNavStepCenterOffset(page: Page, step: number) {
  return page.evaluate((targetStep) => {
    const navList = document.querySelector<HTMLElement>(
      ".group-entries-virtual",
    );
    const target = document.querySelector<HTMLElement>(
      `[data-nav-step="${targetStep}"]`,
    );
    if (!navList || !target) return Number.POSITIVE_INFINITY;
    const navRect = navList.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    return Math.round(
      targetRect.top +
        targetRect.height / 2 -
        (navRect.top + navRect.height / 2),
    );
  }, step);
}

test.describe("Large album editor performance", () => {
  test("opens a 240-step album while keeping rendered media bounded", async ({
    page,
  }) => {
    await mockLargeAlbum(page);
    const start = await page.evaluate(() => performance.now());
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
    const readyMs = await page.evaluate((s) => performance.now() - s, start);
    const renderedMedia = await page.locator("[data-media]").count();

    expect(readyMs).toBeLessThan(15_000);
    expect(renderedMedia).toBeLessThan(80);
  });

  test("jumps across distant steps without mounting the whole album", async ({
    page,
  }) => {
    await mockLargeAlbum(page);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("navigation").getByText("Netherlands").click();
    await expect
      .poll(() => page.locator("[data-nav-step]").count())
      .toBeLessThan(80);

    for (const step of [30, 90, 150, 210]) {
      await scrollNavStepIntoView(page, step);
      await page.locator(`[data-nav-step="${step}"]`).click();
      await expect(page.getByText(`Large Step ${step}`).first()).toBeVisible({
        timeout: 10_000,
      });
      await expect
        .poll(() => page.locator("[data-media]").count())
        .toBeLessThan(120);
    }
  });

  test("keeps the active step near the middle of the nav while scrolling", async ({
    page,
  }) => {
    await mockLargeAlbum(page);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("navigation").getByText("Netherlands").click();

    await scrollNavStepIntoView(page, 180);
    await page.locator(`[data-nav-step="180"]`).click();
    await expect(page.getByText("Large Step 180").first()).toBeVisible({
      timeout: 10_000,
    });
    await page.mouse.move(640, 360);
    await page.mouse.wheel(0, 900);

    await expect
      .poll(() => page.locator("[data-nav-step].visible").textContent())
      .toContain("Large Step");
    const activeStep = await page
      .locator("[data-nav-step].visible")
      .getAttribute("data-nav-step");
    expect(activeStep).not.toBeNull();

    await expect
      .poll(() => activeNavStepCenterOffset(page, Number(activeStep)))
      .toBeGreaterThan(-90);
    await expect
      .poll(() => activeNavStepCenterOffset(page, Number(activeStep)))
      .toBeLessThan(90);
  });
});
