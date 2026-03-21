import type { QuasarLanguage } from "quasar";
import { Lang } from "quasar";
import { watch, type Ref } from "vue";
import i18n, { uiLang } from "@/i18n";

// Discover all Quasar lang packs at build time (~81 locales).
// Vite creates lazy chunks for each - only loaded when needed.
const quasarLangs = import.meta.glob<{ default: QuasarLanguage }>(
  "../../node_modules/quasar/lang/*.js",
);

const packPath = (name: string) => `../../node_modules/quasar/lang/${name}.js`;

/** Available Quasar lang pack codes, extracted from import.meta.glob keys. */
const availableCodes: string[] = Object.keys(quasarLangs)
  .map((p) => p.match(/\/([^/]+)\.js$/)?.[1] ?? "")
  .filter(Boolean)
  .sort();

const availableSet = new Set(availableCodes);

/**
 * Resolve a BCP 47 locale to the closest available Quasar lang pack code.
 * "he-IL" -> "he" (exact match on base language), "pt-BR" -> "pt-BR" (exact).
 */
export function resolveLocale(bcp47: string): string {
  if (availableSet.has(bcp47)) return bcp47;
  const base = bcp47.split("-")[0]!;
  if (availableSet.has(base)) return base;
  return bcp47;
}

async function loadQuasarLang(bcp47: string): Promise<QuasarLanguage> {
  const resolved = resolveLocale(bcp47);
  const loader = quasarLangs[packPath(resolved)] ?? quasarLangs[packPath("en-US")]!;
  return (await loader()).default;
}

/** Self-labeled locale options for the picker (lazy - built on first access). */
let _localeOptions: { label: string; value: string }[] | null = null;
export function getLocaleOptions(): { label: string; value: string }[] {
  if (!_localeOptions) {
    _localeOptions = availableCodes.map((code) => {
      try {
        const selfLang = code.split("-")[0]!;
        const dn = new Intl.DisplayNames([selfLang], { type: "language" });
        return { label: dn.of(code) ?? code, value: code };
      } catch {
        return { label: code, value: code };
      }
    });
  }
  return _localeOptions;
}

/** Tracks the last locale applied - prevents redundant `applyLocale` calls. */
let currentLocale = "";

/** Apply locale globally: vue-i18n messages, Quasar lang pack (+ RTL), HTML lang.
 *  All side effects are deferred until the async pack load succeeds,
 *  so a failed load never leaves the app in a half-applied state. */
export async function applyLocale(bcp47: string): Promise<void> {
  if (bcp47 === currentLocale) return;
  const pack = await loadQuasarLang(bcp47);
  currentLocale = bcp47;
  i18n.global.locale.value = uiLang(bcp47);
  Lang.set(pack);
  document.documentElement.lang = bcp47.split("-")[0]!;
}

/**
 * Reactive locale orchestration - calls `applyLocale` whenever the
 * user's BCP 47 locale ref changes.
 */
export function useLocale(bcp47Locale: Ref<string>) {
  watch(bcp47Locale, (bcp47) => void applyLocale(bcp47), { immediate: true });
}
