import {
  mediaUndoInvalidationKeys,
  useMediaUndo,
} from "@/composables/useMediaUndo";
import { queryKeys } from "@/queries/keys";
import { deferred, withSetup } from "../helpers";
import { server } from "../mocks/server";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { Notify } from "quasar";
import { nextTick } from "vue";

describe("replacement notification", () => {
  it("shows an indefinite info notification while replacement is running", async () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));

    undo.startReplacement();
    await nextTick();

    const notification = document.querySelector(".q-notification");
    expect(notification?.textContent).toContain("Replacing media...");
    expect(notification?.classList.contains("bg-info")).toBe(true);
    expect(notification?.querySelector(".q-spinner")).not.toBeNull();
    undo.clearUndoState();
  });

  it("updates the loading notification to success with Undo and X actions", async () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    const create = vi.spyOn(Notify, "create");
    undo.startReplacement();
    await nextTick();

    undo.rememberReplacement("photo.jpg");
    await nextTick();
    await nextTick();

    expect(create).toHaveBeenCalledOnce();
    const notification = document.querySelector(".q-notification.bg-positive");
    expect(notification?.getAttribute("class")).toContain("bg-positive");
    expect(notification?.querySelector(".q-spinner")).toBeNull();
    expect(notification?.textContent).toContain(
      "Media replaced. Undo is available for 5 minutes.",
    );
    expect(notification?.querySelector("button")?.textContent).toContain("Undo");
    expect(notification?.querySelector('button[aria-label="Close"]')).not.toBeNull();
    undo.clearUndoState();
    create.mockRestore();
  });

  it("updates the loading notification to an error with an X action", async () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();

    undo.failReplacement("Replacement failed. Try again.");
    await nextTick();
    await nextTick();

    const notification = document.querySelector(".q-notification.bg-negative");
    expect(notification?.querySelector(".q-spinner")).toBeNull();
    expect(notification?.textContent).toContain("Replacement failed. Try again.");
    expect(notification?.querySelector('button[aria-label="Close"]')).not.toBeNull();
    undo.clearUndoState();
  });

  it("dismisses the loading notification when replacement is canceled", async () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    await nextTick();

    undo.cancelReplacement();
    await nextTick();

    expect(
      document.querySelector(
        '.q-notification.bg-info:not([class*="leave-active"])',
      ),
    ).toBeNull();
  });

  it("discards the undo opportunity when the success X is clicked", async () => {
    const undo = withSetup(() => useMediaUndo(() => "album-1"));
    undo.startReplacement();
    undo.rememberReplacement("photo.jpg");
    await nextTick();
    await nextTick();

    const close = document.querySelector<HTMLButtonElement>(
      '.q-notification.bg-positive:not([class*="leave-active"]) button[aria-label="Close"]',
    );
    close?.click();
    await nextTick();

    expect(undo.currentUndo.value).toBeNull();
    undo.clearUndoState();
  });

  it("keeps the undo notification open until undo succeeds", async () => {
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
    await nextTick();
    await nextTick();

    const action = document.querySelector<HTMLButtonElement>(
      '.q-notification.bg-positive:not([class*="leave-active"]) button:not([aria-label])',
    );
    action?.click();
    await nextTick();

    expect(
      document.querySelector(
        '.q-notification.bg-positive:not([class*="leave-active"])',
      ),
    ).not.toBeNull();
    request.resolve();
    await flushPromises();
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
