/** Default accent color when no country color is available. */
export const DEFAULT_COUNTRY_COLOR = "#4A90D9";

/** Look up the country color from an album color map, with fallback. */
export function getCountryColor(
  colors: Record<string, string>,
  countryCode: string,
): string {
  return colors[countryCode] ?? DEFAULT_COUNTRY_COLOR;
}
