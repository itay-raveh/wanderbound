import type { RouteLocationNormalized, Router } from "vue-router";

const RETRY_KEY = "chunk-reload-attempted";

export function useChunkErrorRecovery(router: Router): void {
  let pendingTarget: RouteLocationNormalized | null = null;

  router.beforeEach((to) => {
    pendingTarget = to;
  });
  router.afterEach(() => {
    pendingTarget = null;
    sessionStorage.removeItem(RETRY_KEY);
  });

  window.addEventListener("vite:preloadError", (event) => {
    if (!pendingTarget) {
      event.preventDefault();
      return;
    }
    if (sessionStorage.getItem(RETRY_KEY)) return;
    sessionStorage.setItem(RETRY_KEY, String(Date.now()));
    const target = pendingTarget.fullPath;
    if (location.pathname + location.search !== target) {
      location.href = target;
    } else {
      location.reload();
    }
  });
}
