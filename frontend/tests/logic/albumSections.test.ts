import {
  filterCoverFromPages,
  segmentsOverlapping,
  buildSections,
  activeSectionId,
  sectionKey,
  type Section,
} from "@/components/album/albumSections";
import type { DateRange } from "@/client";
import { makeStep, makeSegment } from "../helpers";

// Mock layoutDescription to avoid DOM measurement in tests
vi.mock("@/composables/useTextLayout", () => ({
  layoutDescription: (text: string) => {
    if (!text || text.length < 100) return { pages: [] };
    return { pages: [[], []] }; // 1 sidebar + 1 continuation page
  },
}));

// ---------------------------------------------------------------------------
// filterCoverFromPages
// ---------------------------------------------------------------------------

describe("filterCoverFromPages", () => {
  it("filters cover from pages", () => {
    const pages = [["cover", "p1"], ["p2"]];
    const result = filterCoverFromPages(pages, "cover");
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1"] },
      { originalIdx: 1, page: ["p2"] },
    ]);
  });

  it("removes pages that become empty after cover filtering", () => {
    const pages = [["cover"], ["p1", "p2"]];
    const result = filterCoverFromPages(pages, "cover");
    expect(result).toEqual([{ originalIdx: 1, page: ["p1", "p2"] }]);
  });

  it("handles cover appearing in multiple pages", () => {
    const pages = [["cover", "p1"], ["cover", "p2"], ["p3"]];
    const result = filterCoverFromPages(pages, "cover");
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1"] },
      { originalIdx: 1, page: ["p2"] },
      { originalIdx: 2, page: ["p3"] },
    ]);
  });
});

// ---------------------------------------------------------------------------
// segmentsOverlapping
// ---------------------------------------------------------------------------

describe("segmentsOverlapping", () => {
  const segments = [
    makeSegment({ start_time: 100, end_time: 200 }),
    makeSegment({ start_time: 300, end_time: 400 }),
    makeSegment({ start_time: 500, end_time: 600 }),
  ];

  it("returns segments that overlap the time window", () => {
    const result = segmentsOverlapping(segments, 150, 350);
    expect(result).toHaveLength(2);
    expect(result[0].start_time).toBe(100);
    expect(result[1].start_time).toBe(300);
  });

  it("includes segment when window touches segment start", () => {
    const result = segmentsOverlapping(segments, 50, 100);
    expect(result).toHaveLength(1);
    expect(result[0].start_time).toBe(100);
  });

  it("includes segment when window touches segment end", () => {
    const result = segmentsOverlapping(segments, 200, 250);
    expect(result).toHaveLength(1);
    expect(result[0].start_time).toBe(100);
  });

  it("returns empty when no overlap", () => {
    expect(segmentsOverlapping(segments, 210, 290)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// buildSections
// ---------------------------------------------------------------------------

describe("buildSections", () => {
  it("inserts map section before its first step", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
      makeStep({ id: 2, datetime: "2024-01-20T00:00:00Z", timestamp: 200 }),
      makeStep({ id: 3, datetime: "2024-02-15T00:00:00Z", timestamp: 300 }),
    ];
    const segments = [makeSegment({ start_time: 50, end_time: 250, kind: "driving" })];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    // Map before step 1, then step 1, step 2, step 3
    expect(result).toHaveLength(4);
    expect(result[0].type).toBe("map");
    expect(result[1].type).toBe("step");
    expect(result[2].type).toBe("step");
    expect(result[3].type).toBe("step");
  });

  it("creates hike section when only hike segments (no transport)", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
    ];
    const segments = [makeSegment({ start_time: 50, end_time: 150, kind: "hike" })];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expect(result).toHaveLength(2);
    expect(result[0].type).toBe("hike");
    if (result[0].type === "hike") {
      expect(result[0].hikeSegment.kind).toBe("hike");
    }
  });

  it("creates map section (not hike) when there are transport segments", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
    ];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "hike" }),
      makeSegment({ start_time: 50, end_time: 150, kind: "driving" }),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expect(result).toHaveLength(2);
    expect(result[0].type).toBe("map");
  });

  it("skips ranges with no matching steps", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-03-10T00:00:00Z", timestamp: 100 }),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]]; // no steps in this range
    const result = buildSections(steps, [], ranges);
    // Only the step, no map for the empty range
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("step");
  });

  it("handles multiple map ranges with different steps", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
      makeStep({ id: 2, datetime: "2024-02-10T00:00:00Z", timestamp: 200 }),
    ];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "driving" }),
      makeSegment({ start_time: 150, end_time: 250, kind: "driving" }),
    ];
    const ranges: DateRange[] = [
      ["2024-01-01", "2024-01-31"],
      ["2024-02-01", "2024-02-28"],
    ];

    const result = buildSections(steps, segments, ranges);
    // map1, step1, map2, step2
    expect(result).toHaveLength(4);
    expect(result[0].type).toBe("map");
    expect(result[1].type).toBe("step");
    expect(result[2].type).toBe("map");
    expect(result[3].type).toBe("step");
  });

  it("attaches overlapping segments to map sections", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
      makeStep({ id: 2, datetime: "2024-01-20T00:00:00Z", timestamp: 200 }),
    ];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "driving" }),
      makeSegment({ start_time: 500, end_time: 600, kind: "driving" }), // outside range
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    const mapSection = result.find((s) => s.type === "map");
    expect(mapSection).toBeDefined();
    if (mapSection && mapSection.type === "map") {
      expect(mapSection.segments).toHaveLength(1);
      expect(mapSection.segments[0].start_time).toBe(50);
    }
  });
});

// ---------------------------------------------------------------------------
// activeSectionId - maps virtualizer indices to section identifiers
// ---------------------------------------------------------------------------

describe("activeSectionId", () => {
  const stepSection = (id: number): Section => ({
    type: "step",
    step: makeStep({ id }),
  });
  const mapSection = (dateRange: DateRange): Section => ({
    type: "map",
    steps: [],
    segments: [],
    rangeIdx: 0,
    dateRange,
  });

  it("returns step ID for step sections", () => {
    const sections = [stepSection(42), stepSection(99)];
    expect(activeSectionId(sections, 0)).toBe(42);
    expect(activeSectionId(sections, 1)).toBe(99);
  });

  it("returns section key for map sections", () => {
    const range: DateRange = ["2024-01-01", "2024-01-31"];
    const sections = [mapSection(range), stepSection(1)];
    const result = activeSectionId(sections, 0);
    expect(typeof result).toBe("string");
    expect(result).toBe(sectionKey(sections[0]));
  });
});
