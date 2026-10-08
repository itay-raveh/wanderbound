import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { mockComposedPage, TINY_JPEG_BASE64 } from "../tests/fixtures/mocks";

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
        (_, pageIndex) =>
          mockComposedPage(
            "grid",
            photos.slice(pageIndex * 4, pageIndex * 4 + 4),
          ),
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

async function mockLargeAlbum(
  page: Page,
  chaptered: boolean | number = false,
  locale = "en-US",
) {
  const photosPerStep = chaptered === true ? 16 : PHOTOS_PER_STEP;
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
          locale,
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
        locale,
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
        chapters:
          typeof chaptered === "number"
            ? Array.from({ length: chaptered }, (_, index) => ({
                id: `chapter-${index + 1}`,
                title: `Chapter ${index + 1}`,
                subtitle: "",
                step_ids: steps
                  .slice(
                    (index * STEP_COUNT) / chaptered,
                    ((index + 1) * STEP_COUNT) / chaptered,
                  )
                  .map((step) => step.id),
                front_cover_photo: "",
                back_cover_photo: "",
              }))
            : chaptered
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
  const navList = page.locator(".nav-list");
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
    const navList = document.querySelector<HTMLElement>(".nav-list");
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
  for (const { width, height, locale } of [
    { width: 1600, height: 480, locale: "en-US" },
    { width: 1024, height: 540, locale: "he-IL" },
  ]) {
    test(`one scroller reaches later chapters and final rows at ${width}px in ${locale}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await mockLargeAlbum(page, 40, locale);
      await page.goto("/editor");
      const nav = page.getByRole("navigation");
      const root = nav.locator(".nav-list");
      const finalHeader = nav
        .locator(".chapter-group-header")
        .filter({ hasText: "Chapter 40" });
      await finalHeader.scrollIntoViewIfNeeded();
      await expect(finalHeader).toBeInViewport();
      await finalHeader.focus();
      await page.keyboard.press("Enter");
      const lastRow = nav.locator('[data-nav-step="240"]');
      const firstRow = nav.locator('[data-nav-step="235"]');
      await firstRow.scrollIntoViewIfNeeded();
      await firstRow.hover();
      const beforeWheel = await root.evaluate((el) => el.scrollTop);
      await page.mouse.wheel(0, 300);
      await expect.poll(() => root.evaluate((el) => el.scrollTop)).toBeGreaterThan(beforeWheel);
      await expect(lastRow).toBeInViewport();
      await finalHeader.scrollIntoViewIfNeeded();
      await finalHeader.focus();
      await page.keyboard.press("Enter");
      await expect(lastRow).toHaveCount(0);
      await expect(finalHeader).toBeFocused();
      await expect(finalHeader).toBeInViewport();
      await page.keyboard.press("Enter");
      await firstRow.scrollIntoViewIfNeeded();
      await firstRow.hover();
      await page.mouse.wheel(0, 300);
      await expect(lastRow).toBeInViewport();
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
    });
  }

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
      await expect(page.locator(`[data-nav-step="${step}"]`)).toHaveAttribute("aria-current", "step");
      await expect(page.locator(".album-container .step-name").filter({ hasText: `Large Step ${step}` })).toBeInViewport();
      await expect
        .poll(() => page.locator("[data-media]").count())
        .toBeLessThan(120);
    }
  });

  test("scrolls past the focused step without jumping the sidebar or viewer", async ({
    page,
  }) => {
    await mockLargeAlbum(page);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
    await scrollNavStepIntoView(page, 30);
    const selectedStep = page.locator('[data-nav-step="30"]');
    await selectedStep.click();
    await expect(selectedStep).toBeFocused();
    await expect(selectedStep).toHaveAttribute("aria-current", "step");
    const activePageBaseline = await page.locator(".page-position").textContent();
    // Let the initial navigation and virtual-list measurement settle before
    // measuring user scrolling, including one-frame focus/anchoring jumps.
    await page.waitForTimeout(200);

    const navList = page.locator(".nav-list");
    const trace = await navList.evaluateHandle((el) => {
      const sample = () => ({
        scroll: el.scrollTop,
        top: el.getBoundingClientRect().top,
        viewer: window.scrollY,
        activePage: document.querySelector(".page-position")?.textContent,
      });
      const samples = [sample()];
      let frame = 0;
      const record = () => {
        samples.push(sample());
        frame = requestAnimationFrame(record);
      };
      frame = requestAnimationFrame(record);
      return {
        samples,
        stop: () => cancelAnimationFrame(frame),
      };
    });

    const wheelTarget = await navList.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + 20 };
    });
    await page.mouse.move(wheelTarget.x, wheelTarget.y);
    for (
      let attempt = 0;
      attempt < 8 && (await selectedStep.count());
      attempt++
    ) {
      await page.mouse.wheel(0, 600);
      await page.waitForTimeout(150);
    }
    // Moving offscreen is insufficient: exercise focus recovery when the
    // selected row is actually removed from the virtualized DOM.
    await expect(selectedStep).toHaveCount(0);
    await expect(navList.locator(":focus")).toHaveCount(1);
    const beforeContinuing = await navList.evaluate((el) => el.scrollTop);
    await page.mouse.wheel(0, 600);
    await expect
      .poll(() => navList.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(beforeContinuing);
    await page.waitForTimeout(150);
    const samples = await trace.evaluate((trace) => {
      trace.stop();
      return trace.samples;
    });
    await trace.dispose();

    for (const sample of samples) {
      expect(Math.abs(sample.top - samples[0].top)).toBeLessThanOrEqual(1);
      expect(Math.abs(sample.viewer - samples[0].viewer)).toBeLessThanOrEqual(
        1,
      );
      expect(sample.activePage).toBe(activePageBaseline);
    }
    for (let index = 1; index < samples.length; index++) {
      expect(samples[index].scroll).toBeGreaterThanOrEqual(
        samples[index - 1].scroll - 1,
      );
    }

    const beforeReversing = await navList.evaluate((el) => el.scrollTop);
    await page.mouse.wheel(0, -600);
    await expect
      .poll(() => navList.evaluate((el) => el.scrollTop))
      .toBeLessThan(beforeReversing);
    await page.waitForTimeout(150);
    await expect(page.locator(".page-position")).toHaveText(activePageBaseline!);

    // Focus recovery must leave the rendered steps reachable by keyboard.
    await page.keyboard.press("Tab");
    const keyboardStep = navList.locator("[data-nav-step]:focus");
    await expect(keyboardStep).toHaveCount(1);
    const step = Number(await keyboardStep.getAttribute("data-nav-step"));
    await page.keyboard.press("Enter");
    await expect(keyboardStep).toHaveAttribute("aria-current", "step");
    await expect(page.locator(".album-container .step-name").filter({ hasText: `Large Step ${step}` })).toBeInViewport();
  });

  test("keeps sidebar boundary scrolling out of the album viewer", async ({
    page,
  }) => {
    await mockLargeAlbum(page);
    await page.goto("/editor");
    const entries = page.locator(".nav-list");
    const outer = page.locator(".nav-list");
    await expect(entries).toBeVisible({ timeout: 15_000 });
    const activePageBaseline = await page.locator(".page-position").textContent();

    // The only scroller must reach the last row and contain boundary gestures.
    await entries.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(page.locator('[data-nav-step="240"]')).toHaveCount(1);
    const point = await entries.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      const sidebar = el.closest(".nav-list")!.getBoundingClientRect();
      return {
        x: rect.left + rect.width / 2,
        y: Math.min(rect.bottom, sidebar.bottom, innerHeight) - 30,
      };
    });
    await page.mouse.move(point.x, point.y);
    await page.mouse.wheel(0, 600);
    await expect
      .poll(() => outer.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(0);
    await expect
      .poll(() =>
        outer.evaluate(
          (el) => el.scrollHeight - el.clientHeight - el.scrollTop,
        ),
      )
      .toBeLessThanOrEqual(1);

    // Separate gestures after exhausting the sidebar must not chain to
    // the document and make its active-step sync jump the sidebar backward.
    for (let gesture = 0; gesture < 3; gesture++) {
      await page.waitForTimeout(250);
      await page.mouse.wheel(0, 800);
    }
    await page.waitForTimeout(250);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.locator(".page-position")).toHaveText(activePageBaseline!);
    expect(
      await entries.evaluate(
        (el) => el.scrollHeight - el.clientHeight - el.scrollTop,
      ),
    ).toBeLessThanOrEqual(1);

    // The viewer remains independently scrollable outside the sidebar.
    await page.mouse.move(800, 450);
    await page.mouse.wheel(0, 800);
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(0);
  });

  test("keeps the active step near the middle of the nav while scrolling", async ({
    page,
  }) => {
    await mockLargeAlbum(page, true);
    await page.goto("/editor");
    await expect(page.getByText("Large Album").first()).toBeVisible({
      timeout: 15_000,
    });
    await scrollNavStepIntoView(page, 119);
    await page.locator(`[data-nav-step="119"]`).click();
    await expect(page.getByText("Large Step 119").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator('[data-nav-step="119"]')).toHaveAttribute("aria-current", "step");
    await expect(page.locator(".album-container .step-name").filter({ hasText: "Large Step 119" })).toBeInViewport();
    await page.mouse.move(640, 360);
    await page.mouse.wheel(0, 10000);

    await expect
      .poll(async () =>
        Number(
          await page
            .locator("[data-nav-step].visible")
            .getAttribute("data-nav-step"),
        ),
      )
      .toBeGreaterThan(120);
    const activeStep = await page
      .locator("[data-nav-step].visible")
      .getAttribute("data-nav-step");

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
    await nav.getByText("Chapter 3").scrollIntoViewIfNeeded();
    await expect(nav.getByText("Chapter 3")).toBeInViewport();
    await nav.getByText("Chapter 3").click();

    const chapterCover = nav.locator(
      '[data-nav-section="chapter-chapter-3-cover-front"]',
    );
    segmentPointRequests.length = 0;
    await chapterCover.click();

    await expect(page.locator(".album-container .front-title").filter({ hasText: "Chapter 3" })).toBeInViewport();
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
