/** Canonical font configuration — validated against the API schema. */

import type { Album } from "@/client";

export const ALLOWED_FONTS = ["Frank Ruhl Libre", "Assistant"] as const satisfies
  readonly NonNullable<Album["font"]>[];

export type FontName = (typeof ALLOWED_FONTS)[number];

export const DEFAULT_FONT: FontName = "Assistant";
export const DEFAULT_BODY_FONT: FontName = "Frank Ruhl Libre";

/** CSS fallback stacks keyed by font name. Keep in sync with App.vue :root vars. */
const FONT_FALLBACKS: Record<FontName, string> = {
  "Frank Ruhl Libre": "Georgia, serif",
  "Assistant": "system-ui, -apple-system, sans-serif",
};

/** Build a complete CSS font-family string with fallbacks. */
export function fontStack(name: FontName): string {
  return `"${name}", ${FONT_FALLBACKS[name]}`;
}
