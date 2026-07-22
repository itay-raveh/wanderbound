import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

const API = "**/api/v1";
const STEP_COUNT = 240;
const PHOTOS_PER_STEP = 4;

const mediaBody = Buffer.from(TINY_JPEG_BASE64, "base64");

function photoName(stepIndex: number, photoIndex: number) {
  return `large-step-${stepIndex}-photo-${photoIndex}.jpg`;
}

function makeLargeMedia(photosPerStep = PHOTOS_PER_STEP) {
  const media = [
    { name: "cover.jpg", width: 1920, height: 1080 },
    { name: "back.jpg", width: 1920, height: 1080 },
  ];
  for (let step = 1; step <= STEP_COUNT; step++) {
    for (let photo = 1; photo <= photosPerStep; photo++) {
      media.push({
        name: photoName(step, photo),
        width: photo % 2 === 0 ? 1080 : 1920,
        height: photo % 2 === 0 ? 1920 : 1080,
      });
    }
  }
  return media;
}

function makeLargeSteps(photosPerStep = PHOTOS_PER_STEP) {
  return Array.from({ length: STEP_COUNT }, (_, index) => {
    const stepNumber = index + 1;
    const photos = Array.from({ length: photosPerStep }, (_, photoIndex) =>
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
      pages: Array.from(
        { length: Math.ceil(photos.length / 4) },
        (_, pageIndex) => photos.slice(pageIndex * 4, pageIndex * 4 + 4),
      ),
      unused: [],
      datetime: new Date(timestamp * 1000).toISOString(),
    };
  });
}

function makeLargeSegmentOutlines(steps: ReturnType<typeof makeLargeSteps>) {
  return steps.slice(0, -1).map((step, index) => {
    const nextStep = steps[index + 1];
    return {
      start_time: step.timestamp,
      end_time: nextStep.timestamp,
      kind: "driving",
      timezone_id: "Europe/Amsterdam",
      start_coord: [step.location.lat, step.location.lon],
      end_coord: [nextStep.location.lat, nextStep.location.lon],
    };
  });
}

async function mockLargeAlbum(page: Page, chaptered = false) {
  const photosPerStep = chaptered ? 16 : PHOTOS_PER_STEP;
  const steps = makeLargeSteps(photosPerStep);
  const media = makeLargeMedia(photosPerStep);
  const segmentOutlines = chaptered ? makeLargeSegmentOutlines(steps) : [];
  const segmentPointRequests: string[] = [];
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
        hidden_steps: [],
        hidden_headers: [],
        maps_ranges: [],
        safe_margin_mm: 0,
        chapters: chaptered
          ? [
              {
                id: "chapter-1",
                title: "Large Album",
                subtitle: "Performance fixture",
                step_ids: steps.slice(0, 120).map((step) => step.id),
                front_cover_photo: "cover.jpg",
                back_cover_photo: "back.jpg",
              },
              {
                id: "chapter-2",
                title: "Chapter 2",
                subtitle: "",
                step_ids: steps.slice(120, 180).map((step) => step.id),
                front_cover_photo: "",
                back_cover_photo: "",
              },
              {
                id: "chapter-3",
                title: "Chapter 3",
                subtitle: "",
                step_ids: steps.slice(180).map((step) => step.id),
                front_cover_photo: "",
                back_cover_photo: "",
              },
            ]
          : [
              {
                id: "chapter-1",
                title: "Large Album",
                subtitle: "Performance fixture",
                step_ids: steps.map((step) => step.id),
                front_cover_photo: "cover.jpg",
                back_cover_photo: "back.jpg",
              },
            ],
        colors: { nl: "#e77c31", be: "#3d7a5f", de: "#496b94" },
      },
    }),
  );
  await page.route(`${API}/albums/*/segments`, (route) =>
    route.fulfill({ json: segmentOutlines }),
  );
  await page.route(`${API}/albums/*/segments/points*`, (route) => {
    segmentPointRequests.push(route.request().url());
    return route.fulfill({ json: [] });
  });
  await page.route(`${API}/albums/*/steps`, (route) =>
    route.fulfill({ json: steps }),
  );
  await page.route(`${API}/albums/*/media`, (route) =>
    route.fulfill({ json: media }),
  );
  await page.route("**/media/**", (route) =>
    route.fulfill({ contentType: "image/jpeg", body: mediaBody }),
  );
  return segmentPointRequests;
}

async function scrollNavStepIntoView(page: Page, step: number) {
  const navList = page.locator(".chapter-entries-virtual");
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
      ".chapter-entries-virtual",
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
    test.slow();
    await mockLargeAlbum(page);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
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

  test("defers a distant chapter map until its page is opened", async ({
    page,
  }) => {
    const segmentPointRequests = await mockLargeAlbum(page, true);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });

    const nav = page.getByRole("navigation");
    await expect(nav.getByText("Chapter 3")).toBeVisible();
    await nav.getByText("Chapter 3").click();

    const chapterCover = nav.locator(
      '[data-nav-section="chapter-chapter-3-cover-front"]',
    );
    const beforeScrollY = await page.evaluate(() => window.scrollY);
    await page.evaluate(() => {
      const originalScrollTo = window.scrollTo.bind(window);
      const pageCounts: number[] = [];
      Object.assign(window, { __longJumpPageCounts: pageCounts });
      window.scrollTo = (...args: Parameters<typeof window.scrollTo>) => {
        const top =
          typeof args[0] === "object"
            ? (args[0].top ?? window.scrollY)
            : args[1];
        if (Math.abs(top - window.scrollY) > window.innerHeight * 4) {
          pageCounts.push(document.querySelectorAll(".page-container").length);
        }
        originalScrollTo(...args);
      };
    });
    segmentPointRequests.length = 0;
    await chapterCover.click();

    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(beforeScrollY + 10_000);
    const pageCountsDuringJump = await page.evaluate(
      () =>
        (window as typeof window & { __longJumpPageCounts: number[] })
          .__longJumpPageCounts,
    );
    expect(pageCountsDuringJump).not.toHaveLength(0);
    expect(Math.max(...pageCountsDuringJump)).toBe(0);
    await expect(chapterCover).toHaveClass(/visible/);
    await page.waitForTimeout(2_000);
    expect(segmentPointRequests).toHaveLength(0);

    const chapterThreeHeader = nav
      .locator(".chapter-group-header")
      .filter({ hasText: "Chapter 3" });
    if ((await chapterThreeHeader.getAttribute("aria-expanded")) !== "true") {
      await chapterThreeHeader.click();
    }
    await nav
      .locator('[data-nav-section="chapter-chapter-3-full-map"]')
      .click();
    await expect.poll(() => segmentPointRequests.length).toBeGreaterThan(0);
    await expect
      .poll(() => page.locator("[data-media]").count())
      .toBeLessThan(120);
  });
});
