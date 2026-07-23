import type { RouteLocationNormalized, Router } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChunkErrorRecovery } from "@/composables/useChunkErrorRecovery";

const RETRY_KEY = "chunk-reload-attempted";

function setupPendingRoute() {
  let beforeHook: ((to: RouteLocationNormalized) => void) | undefined;
  let preloadHandler: EventListener | undefined;
  const reload = vi.fn();

  vi.stubGlobal("location", {
    pathname: "/editor",
    search: "",
    href: "/editor",
    reload,
  });
  vi.spyOn(window, "addEventListener").mockImplementation((type, listener) => {
    if (type === "vite:preloadError") {
      preloadHandler = listener as EventListener;
    }
  });

  const router = {
    beforeEach: vi.fn((hook) => {
      beforeHook = hook;
      return vi.fn();
    }),
    afterEach: vi.fn(() => vi.fn()),
  } as unknown as Router;

  useChunkErrorRecovery(router);
  beforeHook?.({ fullPath: "/editor" } as RouteLocationNormalized);

  if (!preloadHandler) throw new Error("preload handler was not registered");
  return { preloadHandler, reload };
}

describe("useChunkErrorRecovery", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("suppresses the first preload error while recovering the pending route", () => {
    const { preloadHandler, reload } = setupPendingRoute();
    const event = new Event("vite:preloadError", { cancelable: true });

    preloadHandler(event);

    expect(event.defaultPrevented).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(RETRY_KEY)).not.toBeNull();
  });

  it("reports a repeated preload error after the recovery attempt", () => {
    const { preloadHandler, reload } = setupPendingRoute();
    sessionStorage.setItem(RETRY_KEY, "attempted");
    const event = new Event("vite:preloadError", { cancelable: true });

    preloadHandler(event);

    expect(event.defaultPrevented).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
