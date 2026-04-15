/** Canonical font configuration - derived from fonts.json registry. */

import fontRegistry from "@fonts";

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

/** Precomputed font-family strings keyed by family name. */
const FONT_STACKS = new Map(
  fontRegistry.fonts.map((f) => [
    f.family,
    `"${f.family}", ${CATEGORY_FALLBACKS[f.category]}`,
  ]),
);

/** Build a complete CSS font-family string with fallbacks. */
export function fontStack(name: string): string {
  return (
    FONT_STACKS.get(name) ?? `"${name}", ${CATEGORY_FALLBACKS["sans-serif"]}`
  );
}
