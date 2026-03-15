import { watch } from "vue";
import { Dark } from "quasar";

const STORAGE_KEY = "album-dark-mode";

export function initDarkMode() {
  const stored = localStorage.getItem(STORAGE_KEY);
  const initial = stored === null || stored === "auto" ? "auto" : stored === "true";
  Dark.set(initial);

  watch(() => Dark.mode, (mode) => {
    localStorage.setItem(STORAGE_KEY, String(mode));
  });
}
