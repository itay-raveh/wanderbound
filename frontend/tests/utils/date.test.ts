import {
  parseLocalDate,
  daysBetween,
  inDateRange,
} from "@/utils/date";

describe("parseLocalDate", () => {
  it("creates a Date at midnight local time from ISO date", () => {
    const d = parseLocalDate("2024-04-12T01:00:00+03:00");
    expect(d.getFullYear()).toBe(2024);
    expect(d.getMonth()).toBe(3); // April = month 3 (0-indexed)
    expect(d.getDate()).toBe(12);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });

});

describe("daysBetween", () => {
  it("handles leap year", () => {
    const a = new Date(2024, 1, 28); // Feb 28
    const b = new Date(2024, 2, 1); // Mar 1
    expect(daysBetween(a, b)).toBe(2); // Feb 29 exists in 2024
  });
});

describe("inDateRange", () => {
  it("returns true for date equal to range start (inclusive)", () => {
    expect(inDateRange("2024-04-01", ["2024-04-01", "2024-04-30"])).toBe(true);
  });

  it("returns true for date equal to range end (inclusive)", () => {
    expect(inDateRange("2024-04-30", ["2024-04-01", "2024-04-30"])).toBe(true);
  });

});
