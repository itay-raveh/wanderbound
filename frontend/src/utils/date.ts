/** Extract the YYYY-MM-DD date part from a datetime string. */
export const isoDate = (datetime: string) => datetime.slice(0, 10);

/** ISO date string → { year, month, day } components. */
export function parseYMD(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = isoDate(iso).split("-").map(Number);
  return { year: year!, month: month!, day: day! };
}

/**
 * Parse the local date from an ISO datetime string without timezone conversion.
 * "2024-04-12T01:00:00+03:00" → Date(2024, 3, 12) at midnight local browser time.
 *
 * Using `new Date(iso)` would convert to browser timezone first, potentially
 * shifting the date when the step's timezone differs from the browser's.
 */
export function parseLocalDate(iso: string): Date {
  const { year, month, day } = parseYMD(iso);
  return new Date(year, month - 1, day);
}

/** Whether an ISO date falls within a [from, to] range (inclusive, string comparison). */
export const inDateRange = (d: string, [from, to]: [string, string]) => d >= from && d <= to;

export function formatShortDate(iso: string): string {
  return parseLocalDate(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** ISO "YYYY-MM-DD" → QDate "YYYY/MM/DD" */
export const toQDate = (iso: string) => iso.replace(/-/g, "/");
/** QDate "YYYY/MM/DD" → ISO "YYYY-MM-DD" */
export const toIso = (qd: string) => qd.replace(/\//g, "-");

/** Quasar range-end YMD object → ISO "YYYY-MM-DD". */
export function ymdToIso({ year, month, day }: { year: number; month: number; day: number }): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** QDate navigation bounds (YYYY/MM) from a sorted step list. */
export function qDateNavBounds(steps: { datetime: string }[]): { min?: string; max?: string } {
  if (!steps.length) return {};
  return {
    min: toQDate(steps[0]!.datetime.slice(0, 7)),
    max: toQDate(steps[steps.length - 1]!.datetime.slice(0, 7)),
  };
}
