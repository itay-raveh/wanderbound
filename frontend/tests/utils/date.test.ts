import {
  parseYMD,
  parseLocalDate,
  daysBetween,
  inDateRange,
  qDateNavBounds,
} from "@/utils/date";

describe("parseYMD", () => {
  it("parses year, month, day from ISO date", () => {
    expect(parseYMD("2024-04-12")).toEqual({ year: 2024, month: 4, day: 12 });
  });
});

describe("parseLocalDate", () => {
  it("creates a Date at midnight local time from ISO date", () => {
    const d = parseLocalDate("2024-04-12T01:00:00+03:00");
    expect(d.getFullYear()).toBe(2024);
    expect(d.getMonth()).toBe(3); // April = month 3 (0-indexed)
    expect(d.getDate()).toBe(12);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });

  it("does not shift date due to timezone offset", () => {
    // If using new Date(iso), this might become April 11 in UTC-heavy timezones.
    // parseLocalDate should always give April 12 regardless of browser timezone.
    const d = parseLocalDate("2024-04-12T01:00:00+03:00");
    expect(d.getDate()).toBe(12);
  });
});

describe("daysBetween", () => {
  it("returns 0 for the same date", () => {
    const d = new Date(2024, 3, 12);
    expect(daysBetween(d, d)).toBe(0);
  });

  it("returns positive days for b > a", () => {
    const a = new Date(2024, 0, 1);
    const b = new Date(2024, 0, 10);
    expect(daysBetween(a, b)).toBe(9);
  });

  it("returns negative days for a > b", () => {
    const a = new Date(2024, 0, 10);
    const b = new Date(2024, 0, 1);
    expect(daysBetween(a, b)).toBe(-9);
  });

  it("handles cross-month boundaries", () => {
    const a = new Date(2024, 0, 31); // Jan 31
    const b = new Date(2024, 1, 1); // Feb 1
    expect(daysBetween(a, b)).toBe(1);
  });

  it("handles leap year", () => {
    const a = new Date(2024, 1, 28); // Feb 28
    const b = new Date(2024, 2, 1); // Mar 1
    expect(daysBetween(a, b)).toBe(2); // Feb 29 exists in 2024
  });
});

describe("inDateRange", () => {
  it("returns true for date inside range", () => {
    expect(inDateRange("2024-04-15", ["2024-04-01", "2024-04-30"])).toBe(true);
  });

  it("returns true for date equal to range start (inclusive)", () => {
    expect(inDateRange("2024-04-01", ["2024-04-01", "2024-04-30"])).toBe(true);
  });

  it("returns true for date equal to range end (inclusive)", () => {
    expect(inDateRange("2024-04-30", ["2024-04-01", "2024-04-30"])).toBe(true);
  });

  it("returns false for date before range", () => {
    expect(inDateRange("2024-03-31", ["2024-04-01", "2024-04-30"])).toBe(false);
  });

  it("returns false for date after range", () => {
    expect(inDateRange("2024-05-01", ["2024-04-01", "2024-04-30"])).toBe(false);
  });

  it("works with same-day range", () => {
    expect(inDateRange("2024-04-15", ["2024-04-15", "2024-04-15"])).toBe(true);
    expect(inDateRange("2024-04-14", ["2024-04-15", "2024-04-15"])).toBe(false);
  });
});

describe("qDateNavBounds", () => {
  it("returns empty object for empty steps array", () => {
    expect(qDateNavBounds([])).toEqual({});
  });

  it("returns min and max from sorted steps", () => {
    const steps = [
      { datetime: "2024-01-15T12:00:00Z" },
      { datetime: "2024-03-20T08:00:00Z" },
      { datetime: "2024-06-01T16:00:00Z" },
    ];
    expect(qDateNavBounds(steps)).toEqual({
      min: "2024/01",
      max: "2024/06",
    });
  });

  it("returns same min and max for single step", () => {
    const steps = [{ datetime: "2024-04-12T10:00:00Z" }];
    expect(qDateNavBounds(steps)).toEqual({
      min: "2024/04",
      max: "2024/04",
    });
  });
});
