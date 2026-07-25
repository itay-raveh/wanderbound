import {
  mediaUndoInvalidationKeys,
  useMediaUndo,
} from "@/composables/useMediaUndo";
import { queryKeys } from "@/queries/keys";
import { deferred, withSetup } from "../helpers";
import { server } from "../mocks/server";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";

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

describe("replacement notification", () => {
  beforeEach(() => {
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
      message: "Replacing media...",
    });
    undo.clearUndoState();
  });

  it("updates the loading notification with our success actions", () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    notify.update.mockClear();
    undo.rememberReplacement("photo.jpg");

    expect(replacementNotification()).toMatchObject({
      timeout: 300_000,
      type: "positive",
      spinner: false,
      message: "Media replaced. Undo is available for 5 minutes.",
      actions: [
        {
          label: "Undo",
          color: "white",
          noDismiss: true,
          handler: expect.any(Function),
        },
        {
          icon: "close",
          color: "white",
          "aria-label": "Close",
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
    undo.rememberReplacement("photo.jpg");

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
    undo.rememberReplacement("photo.jpg");

    const action = replacementNotification().actions[0];
    expect(action.noDismiss).toBe(true);
    action.handler();
    await flushPromises();

    expect(undo.currentUndo.value?.pending).toBe(true);
    request.resolve();
    await flushPromises();
    expect(undo.currentUndo.value).toBeNull();
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
