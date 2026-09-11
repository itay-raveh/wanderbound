import { expect, test, openEditor } from "./fixtures";
import en from "../src/i18n/locales/en.json" with { type: "json" };
import he from "../src/i18n/locales/he.json" with { type: "json" };
import {
  mockAlbum,
  mockStep,
  mockUser,
  mockAuthStateAuthenticated,
} from "../tests/fixtures/mocks";

for (const rtl of [false, true]) {
  test(`reviews PDF pairs without changing the album and restores focus (${rtl ? "RTL" : "LTR"})`, async ({
    authedPage: page,
  }) => {
    test.slow();
    const copy = rtl ? he.print : en.print;
    const pageLabel = (number: number) =>
      copy.pageNumber.replace("{number}", String(number));
    const user = { ...mockUser, locale: rtl ? "he-IL" : "en-US" };
    await page.route("**/api/v1/users", (route) =>
      route.fulfill({ json: user }),
    );
    await page.route("**/api/v1/auth/state", (route) =>
      route.fulfill({ json: { ...mockAuthStateAuthenticated, user } }),
    );
    const step = {
      ...mockStep,
      pages: [{ kind: "panorama_spread", media: ["cover.jpg"] }],
    };
    const album = {
      ...mockAlbum,
      hidden_headers: ["overview", "full-map"],
      chapters: [
        { ...mockAlbum.chapters[0], step_ids: [step.id] },
        {
          ...mockAlbum.chapters[0],
          id: "chapter-2",
          title: "Second chapter",
          step_ids: [2],
        },
      ],
    };
    const mutations: string[] = [];
    page.on("request", (request) => {
      if (["PATCH", "PUT", "POST", "DELETE"].includes(request.method()))
        mutations.push(request.url());
    });
    await page.route("**/api/v1/albums/aid-1", (route) => {
      if (route.request().method() === "PATCH")
        Object.assign(album, route.request().postDataJSON());
      return route.fulfill({ json: album });
    });
    await page.route("**/api/v1/albums/aid-1/steps", (route) =>
      route.fulfill({
        json: [
          step,
          {
            ...step,
            id: 2,
            datetime: "2024-01-11T12:00:00+01:00",
            timestamp: step.timestamp + 864000,
          },
        ],
      }),
    );
    await openEditor(page);
    const trigger = page.getByRole("button", {
      name: copy.preview,
      exact: true,
    });
    const title = page
      .locator('.front-title[contenteditable="plaintext-only"]')
      .first();
    await title.fill("Unapplied title");
    await page.keyboard.press("Control+z");
    await expect(title).toHaveText(mockAlbum.chapters[0].title);
    await title.blur();
    await trigger.click();
    await page.keyboard.press("Control+y");
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("dialog", { name: copy.preview, exact: true }),
    ).toBeHidden();
    await expect(title).toHaveText(mockAlbum.chapters[0].title);
    expect(mutations).toEqual([]);
    await page
      .locator('.front-title[contenteditable="plaintext-only"]')
      .first()
      .fill("Edited chapter");
    await page
      .locator('.front-title[contenteditable="plaintext-only"]')
      .first()
      .blur();
    const undo = page.getByRole("button", {
      name: rtl ? he.shortcuts.undo : en.shortcuts.undo,
      exact: true,
    });
    await expect(undo).toBeEnabled();
    await expect.poll(() => mutations.length).toBe(1);
    mutations.length = 0;
    await trigger.click();
    const dialog = page.getByRole("dialog", {
      name: copy.preview,
      exact: true,
    });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: copy.backToEditor, exact: true }),
    ).toBeFocused();
    await dialog.locator(".q-dialog__inner").focus();
    await page.keyboard.press("Control+z");
    await expect(undo).toBeEnabled();
    await expect(dialog.locator("figcaption")).toHaveText([
      copy.backCover,
      copy.frontCover,
    ]);
    await expect(
      dialog.locator(
        "[contenteditable]:not([contenteditable=false]), .album-action, .cover-drop-overlay",
      ),
    ).toHaveCount(0);
    await page.keyboard.press(rtl ? "ArrowLeft" : "ArrowRight");
    await expect(dialog.locator("figcaption")).toHaveText([
      pageLabel(3),
      pageLabel(4),
    ]);
    await page.keyboard.press(rtl ? "ArrowLeft" : "ArrowRight");
    await expect(dialog.locator(".panorama-page")).toHaveCount(2);
    await expect(dialog.locator("figcaption")).toHaveText([
      pageLabel(5),
      pageLabel(6),
    ]);
    await expect(
      dialog.getByRole("button", { name: copy.nextSpread, exact: true }),
    ).toBeDisabled();
    await expect
      .poll(() =>
        dialog
          .locator(".preview-workspace")
          .evaluate(
            (el) =>
              el.scrollWidth <= el.clientWidth &&
              el.scrollHeight <= el.clientHeight,
          ),
      )
      .toBe(true);
    for (const [width, height, fontSize] of [
      [1024, 384, "16px"],
      [1024, 768, "32px"],
    ] as const) {
      await page.setViewportSize({ width, height });
      await page.evaluate((size) => {
        document.documentElement.style.fontSize = size;
      }, fontSize);
      await expect
        .poll(() =>
          dialog
            .locator(".preview-workspace")
            .evaluate(
              (el) =>
                el.scrollWidth <= el.clientWidth &&
                el.scrollHeight <= el.clientHeight,
            ),
        )
        .toBe(true);
    }
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "";
    });
    await page.setViewportSize({ width: 1600, height: 900 });
    const slots = await dialog
      .locator(".page-slot")
      .evaluateAll((elements) =>
        elements.map((element) => element.getBoundingClientRect().x),
      );
    expect(slots[0] < slots[1]).toBe(!rtl);
    const before = await dialog.locator(".page-slot").first().boundingBox();
    await dialog
      .getByRole("button", { name: copy.zoomIn, exact: true })
      .click();
    const after = await dialog.locator(".page-slot").first().boundingBox();
    expect(after!.width).toBeGreaterThan(before!.width);
    await dialog
      .getByRole("button", { name: copy.fitSpread, exact: true })
      .click();
    await dialog
      .getByLabel(copy.chapter, { exact: true })
      .selectOption("chapter-2");
    await expect(dialog.locator(".front-title")).toHaveText("Second chapter");
    await expect(
      dialog.getByRole("button", { name: copy.previousSpread, exact: true }),
    ).toBeDisabled();
    await dialog
      .getByRole("button", { name: copy.nextSpread, exact: true })
      .click();
    const progress = dialog.locator('.progress-section[role="progressbar"]');
    await expect(progress).toHaveAttribute("aria-valuenow", "1");
    await expect(progress).toHaveAttribute("aria-valuemax", "1");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    expect(mutations).toEqual([]);
  });
}

test("opens the chapter containing the active inserted map", async ({
  authedPage: page,
}) => {
  const second = {
    ...mockStep,
    id: 2,
    datetime: "2024-01-11T12:00:00+01:00",
    timestamp: mockStep.timestamp + 864000,
  };
  await page.route("**/api/v1/albums/aid-1", (route) =>
    route.fulfill({
      json: {
        ...mockAlbum,
        hidden_headers: ["overview", "full-map"],
        maps_ranges: [["2024-01-11", "2024-01-11"]],
        chapters: [
          mockAlbum.chapters[0],
          {
            ...mockAlbum.chapters[0],
            id: "chapter-2",
            title: "Second chapter",
            step_ids: [2],
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/albums/aid-1/steps", (route) =>
    route.fulfill({ json: [mockStep, second] }),
  );
  await openEditor(page);
  await page
    .getByRole("button", { name: "Expand", exact: true })
    .filter({ hasText: "Second chapter" })
    .click();
  await page.getByRole("button", { name: "Map: Jan 11", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Map: Jan 11", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page
    .getByRole("button", { name: "Print preview", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Print preview",
    exact: true,
  });
  await expect(dialog.getByLabel("Chapter", { exact: true })).toHaveValue(
    "chapter-2",
  );
  await expect(dialog.locator(".front-title")).toHaveText("Second chapter");
});
