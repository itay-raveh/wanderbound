import { expect, test } from "./fixtures";
import { mockAlbum, mockSteps } from "../tests/fixtures/mocks";

test("refuses PDF capture when an album font cannot load", async ({
  authedPage: page,
}) => {
  await page.route("**/api/v1/albums/*/print-bundle*", (route) =>
    route.fulfill({
      json: {
        album: {
          ...mockAlbum,
          hidden_headers: ["overview", "full-map"],
          media: [],
        },
        steps: mockSteps.map((step) => ({ ...step, cover: null, pages: [] })),
        segments: [],
        total_distance_km: 0,
      },
    }),
  );
  await page.route("**/fonts/assistant-*", (route) => route.abort());
  await page.emulateMedia({ media: "print" });
  await page.goto("/print/aid-1");
  await page.waitForFunction(() => {
    const state = window as unknown as Record<string, unknown>;
    return state.__PRINT_READY__ || state.__PRINT_ERROR__;
  });
  const state = await page.evaluate(() => {
    const state = window as unknown as Record<string, unknown>;
    return { ready: state.__PRINT_READY__, error: state.__PRINT_ERROR__ };
  });
  expect(state.ready).not.toBe(true);
  expect(state.error).toMatchObject({ code: "font-load-failed" });
});
