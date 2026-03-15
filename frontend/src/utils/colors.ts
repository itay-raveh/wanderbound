/** Default accent color when no country color is available. */
export const DEFAULT_COUNTRY_COLOR = "#4A90D9";

/** Teal accent for distance/exploration widgets on the overview page. */
export const OVERVIEW_DISTANCE_COLOR = "#00897b";

export function getCountryColor(
  colors: Record<string, string>,
  countryCode: string,
): string {
  return colors[countryCode] ?? DEFAULT_COUNTRY_COLOR;
}
