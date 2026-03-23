import {
  filterCoverFromPages,
  segmentsOverlapping,
  sectionKey,
  buildSections,
  sectionPageCount,
  type Section,
} from "@/components/album/albumSections";
import type { DateRange } from "@/client";
import { makeStep, makeSegment } from "../helpers";

// Mock measureDescription to avoid DOM measurement in tests
vi.mock("@/composables/useTextMeasure", () => ({
  measureDescription: (text: string) => {
    // Simple estimate: short if < 100 chars, long otherwise
    if (!text || text.length < 100)
      return { type: "short", mainPageText: text || "", continuationTexts: [] };
    if (text.length < 500)
      return { type: "long", mainPageText: text, continuationTexts: [] };
    return {
      type: "extra-long",
      mainPageText: text.slice(0, 500),
      continuationTexts: [text.slice(500)],
    };
  },
}));

// ---------------------------------------------------------------------------
// filterCoverFromPages
// ---------------------------------------------------------------------------

describe("filterCoverFromPages", () => {
  it("returns all pages with original indices when not short", () => {
    const pages = [["p1", "p2"], ["p3"]];
    const result = filterCoverFromPages(pages, "p1", false);
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1", "p2"] },
      { originalIdx: 1, page: ["p3"] },
    ]);
  });

  it("returns all pages when cover is null", () => {
    const pages = [["p1"], ["p2"]];
    const result = filterCoverFromPages(pages, null, true);
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1"] },
      { originalIdx: 1, page: ["p2"] },
    ]);
  });

  it("returns all pages when cover is undefined", () => {
    const pages = [["p1"]];
    const result = filterCoverFromPages(pages, undefined, true);
    expect(result).toEqual([{ originalIdx: 0, page: ["p1"] }]);
  });

  it("filters cover from pages when short", () => {
    const pages = [["cover", "p1"], ["p2"]];
    const result = filterCoverFromPages(pages, "cover", true);
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1"] },
      { originalIdx: 1, page: ["p2"] },
    ]);
  });

  it("removes pages that become empty after cover filtering", () => {
    const pages = [["cover"], ["p1", "p2"]];
    const result = filterCoverFromPages(pages, "cover", true);
    expect(result).toEqual([{ originalIdx: 1, page: ["p1", "p2"] }]);
  });

  it("handles cover appearing in multiple pages", () => {
    const pages = [["cover", "p1"], ["cover", "p2"], ["p3"]];
    const result = filterCoverFromPages(pages, "cover", true);
    expect(result).toEqual([
      { originalIdx: 0, page: ["p1"] },
      { originalIdx: 1, page: ["p2"] },
      { originalIdx: 2, page: ["p3"] },
    ]);
  });

  it("handles empty pages array", () => {
    expect(filterCoverFromPages([], "cover", true)).toEqual([]);
    expect(filterCoverFromPages([], null, false)).toEqual([]);
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
    expect(result[0]!.start_time).toBe(100);
    expect(result[1]!.start_time).toBe(300);
  });

  it("includes segment when window touches segment start", () => {
    const result = segmentsOverlapping(segments, 50, 100);
    expect(result).toHaveLength(1);
    expect(result[0]!.start_time).toBe(100);
  });

  it("includes segment when window touches segment end", () => {
    const result = segmentsOverlapping(segments, 200, 250);
    expect(result).toHaveLength(1);
    expect(result[0]!.start_time).toBe(100);
  });

  it("returns empty when no overlap", () => {
    expect(segmentsOverlapping(segments, 210, 290)).toEqual([]);
  });

  it("returns all segments when window spans everything", () => {
    expect(segmentsOverlapping(segments, 0, 1000)).toHaveLength(3);
  });

  it("handles empty segments array", () => {
    expect(segmentsOverlapping([], 0, 1000)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// sectionKey
// ---------------------------------------------------------------------------

describe("sectionKey", () => {
  it("generates key for step section", () => {
    const section: Section = { type: "step", step: makeStep({ id: 42 }) };
    expect(sectionKey(section)).toBe("step-42");
  });

  it("generates key for map section", () => {
    const section: Section = {
      type: "map",
      steps: [],
      segments: [],
      rangeIdx: 0,
      dateRange: ["2024-01-01", "2024-01-31"],
    };
    expect(sectionKey(section)).toBe("map-2024-01-01-2024-01-31");
  });

  it("generates key for hike section", () => {
    const section: Section = {
      type: "hike",
      steps: [],
      segments: [],
      hikeSegment: makeSegment({ kind: "hike" }),
      rangeIdx: 0,
      dateRange: ["2024-02-01", "2024-02-15"],
    };
    expect(sectionKey(section)).toBe("hike-2024-02-01-2024-02-15");
  });
});

// ---------------------------------------------------------------------------
// sectionPageCount
// ---------------------------------------------------------------------------

describe("sectionPageCount", () => {
  it("returns 1 for map section", () => {
    const section: Section = {
      type: "map",
      steps: [],
      segments: [],
      rangeIdx: 0,
      dateRange: ["2024-01-01", "2024-01-31"],
    };
    expect(sectionPageCount(section)).toBe(1);
  });

  it("returns 1 for hike section", () => {
    const section: Section = {
      type: "hike",
      steps: [],
      segments: [],
      hikeSegment: makeSegment({ kind: "hike" }),
      rangeIdx: 0,
      dateRange: ["2024-01-01", "2024-01-31"],
    };
    expect(sectionPageCount(section)).toBe(1);
  });

  it("returns 1 + pages for step with short description and no cover", () => {
    // Short description (mocked: < 100 chars), no cover
    // pages: 2 pages => 1 (main) + 2 (photo pages) + 0 (no continuation) = 3
    const section: Section = {
      type: "step",
      step: makeStep({
        description: "Short",
        cover: null,
        pages: [["p1"], ["p2"]],
      }),
    };
    expect(sectionPageCount(section)).toBe(3);
  });

  it("accounts for cover removal from pages in short layout", () => {
    // Short description, cover = "p1" which is in pages
    // Pages before filter: [["p1"], ["p2"]]
    // After filter (short + cover): [["p1"]] filtered to [] (removed), [["p2"]] stays
    // So 1 remaining page => 1 (main) + 1 (filtered pages) + 0 (continuations) = 2
    const section: Section = {
      type: "step",
      step: makeStep({
        description: "Short",
        cover: "p1",
        pages: [["p1"], ["p2"]],
      }),
    };
    expect(sectionPageCount(section)).toBe(2);
  });

  it("counts continuation texts in page count", () => {
    // Extra-long description (mocked: > 500 chars) => 1 continuation text
    const longText = "x".repeat(600);
    const section: Section = {
      type: "step",
      step: makeStep({
        description: longText,
        pages: [["p1"]],
      }),
    };
    // 1 (main) + 1 (pages) + 1 (continuation) = 3
    expect(sectionPageCount(section)).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// buildSections
// ---------------------------------------------------------------------------

describe("buildSections", () => {
  it("returns only step sections when no map ranges", () => {
    const steps = [makeStep({ id: 1 }), makeStep({ id: 2 })];
    const result = buildSections(steps, [], []);
    expect(result).toHaveLength(2);
    expect(result.every((s) => s.type === "step")).toBe(true);
  });

  it("returns empty for empty inputs", () => {
    expect(buildSections([], [], [])).toEqual([]);
  });

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
    expect(result[0]!.type).toBe("map");
    expect(result[1]!.type).toBe("step");
    expect(result[2]!.type).toBe("step");
    expect(result[3]!.type).toBe("step");
  });

  it("creates hike section when only hike segments (no transport)", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
    ];
    const segments = [makeSegment({ start_time: 50, end_time: 150, kind: "hike" })];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expect(result).toHaveLength(2);
    expect(result[0]!.type).toBe("hike");
    if (result[0]!.type === "hike") {
      expect(result[0]!.hikeSegment.kind).toBe("hike");
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
    expect(result[0]!.type).toBe("map");
  });

  it("creates map section (not hike) when there are flight segments", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
    ];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "hike" }),
      makeSegment({ start_time: 50, end_time: 150, kind: "flight" }),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expect(result[0]!.type).toBe("map");
  });

  it("skips ranges with no matching steps", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-03-10T00:00:00Z", timestamp: 100 }),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]]; // no steps in this range
    const result = buildSections(steps, [], ranges);
    // Only the step, no map for the empty range
    expect(result).toHaveLength(1);
    expect(result[0]!.type).toBe("step");
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
    expect(result[0]!.type).toBe("map");
    expect(result[1]!.type).toBe("step");
    expect(result[2]!.type).toBe("map");
    expect(result[3]!.type).toBe("step");
  });

  it("preserves rangeIdx in map sections", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z", timestamp: 100 }),
      makeStep({ id: 2, datetime: "2024-02-10T00:00:00Z", timestamp: 200 }),
    ];
    const ranges: DateRange[] = [
      ["2024-01-01", "2024-01-31"],
      ["2024-02-01", "2024-02-28"],
    ];

    const result = buildSections(steps, [], ranges);
    const maps = result.filter(
      (s): s is Extract<Section, { rangeIdx: number }> => s.type === "map" || s.type === "hike",
    );
    expect(maps).toHaveLength(2);
    expect(maps[0]!.rangeIdx).toBe(0);
    expect(maps[1]!.rangeIdx).toBe(1);
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
      expect(mapSection.segments[0]!.start_time).toBe(50);
    }
  });
});
