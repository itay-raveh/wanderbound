import {
  mediaUndoInvalidationKeys,
  useMediaUndo,
} from "@/composables/useMediaUndo";
import { queryKeys } from "@/queries/keys";
import { deferred, withSetup } from "../helpers";
import { server } from "../mocks/server";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import i18n from "@/i18n";

const notify = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
}));

vi.mock("quasar", async (importOriginal) => {
  const actual = await importOriginal<typeof import("quasar")>();
  return {
    ...actual,
    Notify: { ...actual.Notify, create: notify.create },
  };
});

function replacementNotification() {
  return notify.update.mock.calls.at(-1)?.[0];
}

const replacement = {
  mediaName: "photo.jpg",
  previous: { width: 1920, height: 1080, byteSize: 1234 },
  replacement: { width: 3000, height: 2000, byteSize: 12_345 },
};

describe("replacement notification", () => {
  beforeEach(() => {
    i18n.global.locale.value = "en";
    notify.create.mockReset();
    notify.update.mockReset();
    notify.create.mockReturnValue(notify.update);
  });

  it("reports replacement progress, then shows the file receipt and choices", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));

    undo.startReplacement();

    expect(notify.create).toHaveBeenCalledWith(
      expect.objectContaining({
        spinner: true,
        message: "Replacing media…",
      }),
    );
    notify.update.mockClear();

    undo.rememberReplacement(replacement);

    expect(replacementNotification()).toMatchObject({
      spinner: false,
      message: "Media replaced",
      caption:
        "\u20661,920 × 1,080 · 1.2KB\u2069 → \u20663,000 × 2,000 · 12.1KB\u2069",
      actions: [
        {
          label: "Undo",
          handler: expect.any(Function),
        },
        {
          label: "Keep replacement",
          handler: expect.any(Function),
        },
      ],
    });
    undo.clearUndoState();
  });

  it("reports a replacement failure without offering Undo", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    notify.update.mockClear();
    undo.failReplacement("Replacement failed. Try again.");

    expect(replacementNotification()).toMatchObject({
      spinner: false,
      message: "Replacement failed. Try again.",
    });
    expect(
      replacementNotification().actions.some(
        (action: { label?: string }) => action.label === "Undo",
      ),
    ).toBe(false);
    expect(undo.currentUndo.value).toBeNull();
    undo.clearUndoState();
  });

  it("discards the undo opportunity when Keep replacement is chosen", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    const keep = replacementNotification().actions.find(
      (action: { label?: string }) => action.label === "Keep replacement",
    );
    keep.handler();

    expect(undo.currentUndo.value).toBeNull();
  });

  it("sends one undo request and keeps it pending until completion", async () => {
    const request = deferred<void>();
    let requests = 0;
    server.use(
      http.post(
        "http://localhost:8000/api/v1/albums/album-1/external-media/undo/photo.jpg",
        async () => {
          requests += 1;
          await request.promise;
          return HttpResponse.json({});
        },
      ),
    );
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    void undo.undo();
    void undo.undo();
    await flushPromises();

    expect(requests).toBe(1);
    expect(undo.currentUndo.value?.pending).toBe(true);
    request.resolve();
    await flushPromises();
    expect(undo.currentUndo.value).toBeNull();
  });

  it("offers a working retry after an undo request fails", async () => {
    let attempts = 0;
    server.use(
      http.post(
        "http://localhost:8000/api/v1/albums/album-1/external-media/undo/photo.jpg",
        () => {
          attempts += 1;
          return attempts === 1
            ? HttpResponse.json({}, { status: 500 })
            : HttpResponse.json({});
        },
      ),
    );
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    await undo.undo();
    await flushPromises();

    expect(undo.currentUndo.value?.pending).toBe(false);
    const retry = replacementNotification().actions.find(
      (action: { label?: string }) => action.label === "Try undo again",
    );
    retry.handler();
    await flushPromises();

    expect(attempts).toBe(2);
    expect(undo.currentUndo.value).toBeNull();
  });

  it("keeps the numeric receipt isolated in the Hebrew interface", () => {
    i18n.global.locale.value = "he";
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    expect(replacementNotification()).toMatchObject({
      message: "המדיה הוחלפה",
      caption:
        "\u20661,920 × 1,080 · 1.2KB\u2069 ← \u20663,000 × 2,000 · 12.1KB\u2069",
      actions: expect.arrayContaining([
        expect.objectContaining({
          label: "שמירת ההחלפה",
        }),
        expect.objectContaining({ label: "ביטול ההחלפה" }),
      ]),
    });
    undo.clearUndoState();
  });
});

describe("mediaUndoInvalidationKeys", () => {
  it("invalidates print bundle after replacement undo", () => {
    expect(mediaUndoInvalidationKeys("album-1")).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
      queryKeys.steps("album-1"),
      queryKeys.printBundles("album-1"),
    ]);
  });
});
