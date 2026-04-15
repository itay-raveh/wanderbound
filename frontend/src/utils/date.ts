/** Extract the YYYY-MM-DD date part from a datetime string. */
export const isoDate = (datetime: string) => datetime.slice(0, 10);

/** ISO date string -> { year, month, day } components. */
export function parseYMD(iso: string): {
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

/** ISO "YYYY-MM-DD" -> QDate "YYYY/MM/DD" */
export const toQDate = (iso: string) => iso.replace(/-/g, "/");
/** QDate "YYYY/MM/DD" -> ISO "YYYY-MM-DD" */
export const toIso = (qd: string) => qd.replace(/\//g, "-");

export const SHORT_DATE: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
};

/** Quasar range-end YMD object -> ISO "YYYY-MM-DD". */
export function ymdToIso({
  year,
  month,
  day,
}: {
  year: number;
  month: number;
  day: number;
}): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Advance an ISO date by one calendar day. */
function nextCalendarDay(iso: string): string {
  const d = new Date(iso + "T12:00:00"); // Noon avoids DST edge cases
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** Group sorted ISO dates into contiguous [from, to] ranges (adjacent calendar days merge). */
export function datesToRanges(dates: string[]): [string, string][] {
  if (!dates.length) return [];
  const sorted = [...new Set(dates)].sort();
  const ranges: [string, string][] = [];
  let start = sorted[0];
  let end = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    const d = sorted[i];
    if (d <= nextCalendarDay(end)) {
      end = d;
    } else {
      ranges.push([start, end]);
      start = d;
      end = d;
    }
  }
  ranges.push([start, end]);
  return ranges;
}

/** QDate navigation bounds (YYYY/MM) from a sorted step list. */
export function qDateNavBounds(steps: { datetime: string }[]): {
  min?: string;
  max?: string;
} {
  if (!steps.length) return {};
  return {
    min: toQDate(steps[0].datetime.slice(0, 7)),
    max: toQDate(steps[steps.length - 1].datetime.slice(0, 7)),
  };
}
