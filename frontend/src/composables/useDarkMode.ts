import { useStorage } from "@vueuse/core";
import { Dark } from "quasar";
import { watchEffect } from "vue";
import { DARK_MODE_KEY } from "@/utils/storage-keys";

type DarkModePref = "system" | "light" | "dark";

export function useDarkMode() {
  const pref = useStorage<DarkModePref>(DARK_MODE_KEY, "system");
  watchEffect(() => {
    Dark.set(pref.value === "system" ? "auto" : pref.value === "dark");
  });
  return pref;
}
