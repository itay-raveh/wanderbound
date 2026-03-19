import type { QuasarLanguage } from "quasar";
import { Lang } from "quasar";
import { watch, type Ref } from "vue";
import i18n, { uiLang } from "@/i18n";

// Discover all Quasar lang packs at build time (~81 locales).
// Vite creates lazy chunks for each — only loaded when needed.
const quasarLangs = import.meta.glob<{ default: QuasarLanguage }>(
  "../../node_modules/quasar/lang/*.js",
);

const packPath = (name: string) => `../../node_modules/quasar/lang/${name}.js`;

async function loadQuasarLang(bcp47: string): Promise<QuasarLanguage> {
  const lang = bcp47.split("-")[0]!;
  const loader =
    quasarLangs[packPath(bcp47)] ??
    quasarLangs[packPath(lang)] ??
    quasarLangs[packPath("en-US")]!;
  return (await loader()).default;
}

/** Self-labeled locale options for the picker (lazy — built on first access). */
let _localeOptions: { label: string; value: string }[] | null = null;
export function getLocaleOptions(): { label: string; value: string }[] {
  if (!_localeOptions) {
    const availableLocales = Object.keys(quasarLangs)
      .map((p) => p.match(/\/([^/]+)\.js$/)?.[1] ?? "")
      .filter(Boolean)
      .sort();
    _localeOptions = availableLocales.map((code) => {
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

/** Tracks the last locale applied — prevents redundant `applyLocale` calls. */
let currentLocale = "";

/** Apply locale globally: vue-i18n messages, Quasar lang pack (+ RTL), HTML lang. */
export async function applyLocale(bcp47: string): Promise<void> {
  if (bcp47 === currentLocale) return;
  currentLocale = bcp47;
  i18n.global.locale.value = uiLang(bcp47);
  const pack = await loadQuasarLang(bcp47);
  Lang.set(pack);
  document.documentElement.lang = bcp47.split("-")[0]!;
}

/**
 * Reactive locale orchestration — calls `applyLocale` whenever the
 * user's BCP 47 locale ref changes.
 */
export function useLocale(bcp47Locale: Ref<string>) {
  watch(bcp47Locale, (bcp47) => void applyLocale(bcp47), { immediate: true });
}
