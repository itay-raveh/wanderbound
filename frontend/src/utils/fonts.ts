/** Canonical font configuration — derived from fonts.json registry. */

import fontRegistry from "../../fonts.json";

/** All available font family names, ordered as declared in fonts.json. */
export const ALLOWED_FONTS = fontRegistry.fonts.map((f) => f.family);

export const DEFAULT_FONT = fontRegistry.defaults.heading;
export const DEFAULT_BODY_FONT = fontRegistry.defaults.body;

const CATEGORY_FALLBACKS: Record<string, string> = {
  serif: "Georgia, serif",
  "sans-serif": "system-ui, -apple-system, sans-serif",
  display: "cursive, sans-serif",
  monospace: "ui-monospace, monospace",
};

/** Build a complete CSS font-family string with fallbacks. */
export function fontStack(name: string): string {
  const entry = fontRegistry.fonts.find((f) => f.family === name);
  const fallback = CATEGORY_FALLBACKS[entry?.category ?? "sans-serif"];
  return `"${name}", ${fallback}`;
}
