/** Default accent color when no country color is available. */
export const DEFAULT_COUNTRY_COLOR = "#4A90D9";

export const STAT_COLORS = {
  distance: "#00897b",
  cold: "#42a5f5",
  hot: "#ef6c00",
  elevation: "#8d6e63",
} as const;

export function getCountryColor(
  colors: Record<string, string>,
  countryCode: string,
): string {
  return colors[countryCode] ?? DEFAULT_COUNTRY_COLOR;
}

/**
 * Parse a hex color string (#RGB or #RRGGBB) into [r, g, b] in 0–255.
 */
function parseHex(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;

  return [h, s, l];
}

function hslToHex(h: number, s: number, l: number): string {
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };

  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  const toHex = (v: number) =>
    Math.round(v * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

const MIN_SATELLITE_LIGHTNESS = 0.45;
const MIN_SATELLITE_SATURATION = 0.5;

/**
 * Ensure a hex color is bright and saturated enough to be visible on dark
 * satellite imagery. If the color is too dark or desaturated, it is shifted
 * to meet minimum lightness and saturation thresholds.
 */
export function ensureSatelliteContrast(hex: string): string {
  const [r, g, b] = parseHex(hex);
  const [h, rawS, rawL] = rgbToHsl(r, g, b);

  if (rawL >= MIN_SATELLITE_LIGHTNESS && rawS >= MIN_SATELLITE_SATURATION) return hex;

  const s = Math.max(rawS, MIN_SATELLITE_SATURATION);
  const l = Math.max(rawL, MIN_SATELLITE_LIGHTNESS);
  return hslToHex(h, s, l);
}

/**
 * Mute a hex color for the overview page's dark background.
 * Caps saturation and clamps lightness into a narrow pastel range,
 * producing a hand-illustrated atlas feel while preserving hue.
 */
export function toOverviewTone(hex: string): string {
  const [r, g, b] = parseHex(hex);
  const [h, rawS, rawL] = rgbToHsl(r, g, b);
  const s = Math.min(rawS, 0.35);
  const l = Math.max(Math.min(rawL, 0.65), 0.55);
  return hslToHex(h, s, l);
}
