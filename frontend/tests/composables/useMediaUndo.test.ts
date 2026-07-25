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

  it("starts an indefinite loading notification", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));

    undo.startReplacement();

    expect(notify.create).toHaveBeenCalledWith({
      group: false,
      timeout: 0,
      type: "info",
      spinner: true,
      message: "Replacing media…",
    });
    undo.clearUndoState();
  });

  it("updates the loading notification with our success actions", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    notify.update.mockClear();
    undo.rememberReplacement(replacement);

    expect(replacementNotification()).toMatchObject({
      timeout: 300_000,
      type: "positive",
      spinner: false,
      message: "Media replaced",
      caption:
        "\u20661,920 × 1,080 · 1.2KB\u2069 → \u20663,000 × 2,000 · 12.1KB\u2069",
      actions: [
        {
          label: "Undo",
          color: "white",
          noDismiss: true,
          handler: expect.any(Function),
        },
        {
          label: "Keep replacement",
          color: "white",
          handler: expect.any(Function),
        },
      ],
    });
    undo.clearUndoState();
  });

  it("updates the loading notification with our error state", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    notify.update.mockClear();
    undo.failReplacement("Replacement failed. Try again.");

    expect(replacementNotification()).toMatchObject({
      timeout: 5000,
      type: "negative",
      spinner: false,
      message: "Replacement failed. Try again.",
      actions: [
        {
          icon: "close",
          "aria-label": "Close",
          handler: expect.any(Function),
        },
      ],
    });
    undo.clearUndoState();
  });

  it("dismisses the loading notification when replacement is canceled", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    notify.update.mockClear();
    undo.cancelReplacement();

    expect(notify.update).toHaveBeenCalledWith();
  });

  it("discards the undo opportunity when our close action runs", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    const close = replacementNotification().actions[1];
    close.handler();

    expect(undo.currentUndo.value).toBeNull();
    expect(notify.update).toHaveBeenLastCalledWith();
  });

  it("keeps replacement undo pending until our request succeeds", async () => {
    const request = deferred<void>();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/albums/album-1/external-media/undo/photo.jpg",
        async () => {
          await request.promise;
          return HttpResponse.json({});
        },
      ),
    );
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    const action = replacementNotification().actions[0];
    expect(action.noDismiss).toBe(true);
    action.handler();
    await flushPromises();

    expect(undo.currentUndo.value?.pending).toBe(true);
    expect(replacementNotification()).toMatchObject({
      timeout: 0,
      type: "info",
      spinner: true,
      message: "Undoing replacement…",
      actions: [],
    });
    request.resolve();
    await flushPromises();
    expect(undo.currentUndo.value).toBeNull();
  });

  it("keeps Undo recoverable after a failed request", async () => {
    server.use(
      http.post(
        "http://localhost:8000/api/v1/albums/album-1/external-media/undo/photo.jpg",
        () => HttpResponse.json({}, { status: 500 }),
      ),
    );
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement(replacement);

    replacementNotification().actions[0].handler();
    await flushPromises();

    expect(undo.currentUndo.value?.pending).toBe(false);
    expect(replacementNotification()).toMatchObject({
      timeout: 0,
      type: "negative",
      spinner: false,
      message: "Undo failed. Try again.",
      actions: [
        { label: "Try undo again", handler: expect.any(Function) },
        {
          label: "Keep replacement",
          handler: expect.any(Function),
        },
      ],
    });
    undo.clearUndoState();
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
