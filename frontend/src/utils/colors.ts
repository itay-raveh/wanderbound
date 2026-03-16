/** Default accent color when no country color is available. */
export const DEFAULT_COUNTRY_COLOR = "#4A90D9";

export const STAT_COLORS = {
  days: "#3f51b5",
  distance: "#00897b",
  photos: "#e65100",
  steps: "#8e24aa",
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
