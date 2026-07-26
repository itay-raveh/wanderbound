/** Extract the YYYY-MM-DD date part from a datetime string. */
export const isoDate = (datetime: string) => datetime.slice(0, 10);

/** ISO date string -> { year, month, day } components. */
function parseYMD(iso: string): {
  year: number;
  month: number;
  day: number;
} {
  const [year, month, day] = isoDate(iso).split("-").map(Number);
  return { year: year, month: month, day: day };
}

/**
 * Parse the local date from an ISO datetime string without timezone conversion.
 * "2024-04-12T01:00:00+03:00" -> Date(2024, 3, 12) at midnight local browser time.
 *
 * Using `new Date(iso)` would convert to browser timezone first, potentially
 * shifting the date when the step's timezone differs from the browser's.
 */
export function parseLocalDate(iso: string): Date {
  const { year, month, day } = parseYMD(iso);
  return new Date(year, month - 1, day);
}

/** Whole days between two Dates (truncated, not rounded). */
export function daysBetween(a: Date, b: Date): number {
  return Math.floor((b.getTime() - a.getTime()) / 86_400_000);
}

/** Whether an ISO date falls within a [from, to] range (inclusive, string comparison). */
export const inDateRange = (d: string, [from, to]: [string, string]) =>
  d >= from && d <= to;

export const SHORT_DATE: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
};
