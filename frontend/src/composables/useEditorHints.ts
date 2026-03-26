import { ref, readonly } from "vue";

function tryStorage(fn: () => void) {
  try { fn(); } catch { /* private browsing / quota exceeded */ }
}

function makeHint(key: string) {
  let initial = false;
  try { initial = localStorage.getItem(key) === "1"; } catch {}
  const dismissed = ref(initial);
  const dismiss = () => { dismissed.value = true; tryStorage(() => localStorage.setItem(key, "1")); };
  const reset = () => { dismissed.value = false; tryStorage(() => localStorage.removeItem(key)); };
  return { dismissed: readonly(dismissed), dismiss, reset };
}

const editor = makeHint("onboarding-editor-dismissed");
const map = makeHint("onboarding-map-dismissed");

export function useEditorHints() {
  function resetHints() {
    editor.reset();
    map.reset();
  }

  return {
    bannerDismissed: editor.dismissed,
    mapBannerDismissed: map.dismissed,
    dismissBanner: editor.dismiss,
    dismissMapBanner: map.dismiss,
    resetHints,
  };
}
