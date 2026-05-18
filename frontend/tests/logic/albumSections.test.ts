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

vi.mock("@/composables/useTextLayout", () => ({
  layoutDescription: (text: string) => {
    if (!text || text.length < 100) return { pages: [] };
    return { pages: [[], []] };
  },
}));

const expectTypes = (sections: Section[], types: Section["type"][]) => {
  expect(sections.map((section) => section.type)).toEqual(types);
};

const stepAt = (id: number, datetime: string, timestamp = id * 100) =>
  makeStep({ id, datetime, timestamp });

const drivingSegment = (start_time: number, end_time: number) =>
  makeSegment({ start_time, end_time, kind: "driving" });

describe("filterCoverFromPages", () => {
  it.each([
    [
      [["cover", "p1"], ["p2"]],
      [
        { originalIdx: 0, page: ["p1"] },
        { originalIdx: 1, page: ["p2"] },
      ],
    ],
    [[["cover"], ["p1", "p2"]], [{ originalIdx: 1, page: ["p1", "p2"] }]],
    [
      [["cover", "p1"], ["cover", "p2"], ["p3"]],
      [
        { originalIdx: 0, page: ["p1"] },
        { originalIdx: 1, page: ["p2"] },
        { originalIdx: 2, page: ["p3"] },
      ],
    ],
  ])("filters cover entries from %j", (pages, expected) => {
    expect(filterCoverFromPages(pages, "cover")).toEqual(expected);
  });
});

describe("segmentsOverlapping", () => {
  const segments = [
    makeSegment({ start_time: 100, end_time: 200 }),
    makeSegment({ start_time: 300, end_time: 400 }),
    makeSegment({ start_time: 500, end_time: 600 }),
  ];

  it.each([
    [150, 350, [100, 300]],
    [50, 100, [100]],
    [200, 250, [100]],
    [210, 290, []],
  ])("returns overlaps for %s..%s", (from, to, starts) => {
    expect(
      segmentsOverlapping(segments, from, to).map(
        (segment) => segment.start_time,
      ),
    ).toEqual(starts);
  });
});

describe("buildSections", () => {
  it("inserts map section before its first step", () => {
    const steps = [
      stepAt(1, "2024-01-10T00:00:00Z"),
      stepAt(2, "2024-01-20T00:00:00Z"),
      stepAt(3, "2024-02-15T00:00:00Z"),
    ];
    const segments = [drivingSegment(50, 250)];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expectTypes(result, ["map", "step", "step", "step"]);
  });

  it("creates hike section when only hike segments (no transport)", () => {
    const steps = [stepAt(1, "2024-01-10T00:00:00Z")];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "hike" }),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expectTypes(result, ["hike", "step"]);
    if (result[0].type === "hike") {
      expect(result[0].hikeSegment.kind).toBe("hike");
    }
  });

  it("creates map section (not hike) when there are transport segments", () => {
    const steps = [stepAt(1, "2024-01-10T00:00:00Z")];
    const segments = [
      makeSegment({ start_time: 50, end_time: 150, kind: "hike" }),
      drivingSegment(50, 150),
    ];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];

    const result = buildSections(steps, segments, ranges);
    expectTypes(result, ["map", "step"]);
  });

  it("skips ranges with no matching steps", () => {
    const steps = [stepAt(1, "2024-03-10T00:00:00Z")];
    const ranges: DateRange[] = [["2024-01-01", "2024-01-31"]];
    const result = buildSections(steps, [], ranges);
    expectTypes(result, ["step"]);
  });

  it("handles multiple map ranges with different steps", () => {
    const steps = [
      stepAt(1, "2024-01-10T00:00:00Z"),
      stepAt(2, "2024-02-10T00:00:00Z"),
    ];
    const segments = [drivingSegment(50, 150), drivingSegment(150, 250)];
    const ranges: DateRange[] = [
      ["2024-01-01", "2024-01-31"],
      ["2024-02-01", "2024-02-28"],
    ];

    const result = buildSections(steps, segments, ranges);
    expectTypes(result, ["map", "step", "map", "step"]);
  });

  it("attaches overlapping segments to map sections", () => {
    const steps = [
      stepAt(1, "2024-01-10T00:00:00Z"),
      stepAt(2, "2024-01-20T00:00:00Z"),
    ];
    const segments = [drivingSegment(50, 150), drivingSegment(500, 600)];
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
