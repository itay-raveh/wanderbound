import { createI18n } from "vue-i18n";
import en from "./locales/en.json";
import he from "./locales/he.json";
import de from "./locales/de.json";

const messages = { en, he, de };
type MessageLanguage = keyof typeof messages;

export function uiLang(bcp47: string): MessageLanguage {
  const lang = bcp47.split("-")[0] ?? "";
  return Object.hasOwn(messages, lang) ? (lang as MessageLanguage) : "en";
}

const i18n = createI18n({
  legacy: false,
  locale: "en",
  fallbackLocale: "en",
  messages,
});

/** Global translate function for use outside component setup (composables, mutations). */
export const t = i18n.global.t;

export default i18n;
