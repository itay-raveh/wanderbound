import { createI18n } from "vue-i18n";
import en from "./locales/en.json";
import he from "./locales/he.json";
import de from "./locales/de.json";

/** Map BCP 47 locale to vue-i18n message language. Only "he" and "de" have translations; everything else -> "en". */
export function uiLang(bcp47: string): "en" | "he" | "de" {
  const lang = bcp47.split("-")[0];
  return lang === "he" || lang === "de" ? lang : "en";
}

const i18n = createI18n({
  legacy: false,
  locale: "en",
  fallbackLocale: "en",
  messages: { en, he, de },
});

/** Global translate function for use outside component setup (composables, mutations). */
export const t = i18n.global.t;

export default i18n;