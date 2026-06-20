import { buildChapterGroups } from "@/components/editor/nav/useAlbumNavGroups";
import type { AlbumChapter, DateRange } from "@/client";
import { makeStep } from "../helpers";

const stepItems = [
  {
    id: 1,
    name: "One",
    country: "AR",
    countryLabel: "Argentina",
    color: "#111111",
    date: new Date("2024-01-01T00:00:00Z"),
    thumb: null,
    detail: "",
  },
  {
    id: 2,
    name: "Two",
    country: "AR",
    countryLabel: "Argentina",
    color: "#111111",
    date: new Date("2024-01-02T00:00:00Z"),
    thumb: null,
    detail: "",
  },
  {
    id: 3,
    name: "Three",
    country: "CL",
    countryLabel: "Chile",
    color: "#222222",
    date: new Date("2024-02-01T00:00:00Z"),
    thumb: null,
    detail: "",
  },
];

describe("buildChapterGroups", () => {
  it("builds chapter groups with scoped map entries", () => {
    const steps = [
      makeStep({ id: 1, datetime: "2024-01-01T00:00:00Z" }),
      makeStep({ id: 2, datetime: "2024-01-02T00:00:00Z" }),
      makeStep({ id: 3, datetime: "2024-02-01T00:00:00Z" }),
    ];
    const chapters: AlbumChapter[] = [
      {
        id: "chapter-1",
        title: "First",
        subtitle: null,
        step_ids: [1, 2],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
    ];
    const mapsRanges: DateRange[] = [
      ["2024-01-01", "2024-01-31"],
      ["2024-02-01", "2024-02-28"],
    ];

    const groups = buildChapterGroups({
      steps,
      stepItems,
      mapsRanges,
      chapters,
      untitledLabel: (index) => `Chapter ${index + 1}`,
      dateRangeLabel: (first, last) =>
        `${first.toISOString()} - ${last.toISOString()}`,
    });

    expect(groups).toHaveLength(1);
    expect(groups[0].name).toBe("First");
    expect(groups[0].stepIds).toEqual([1, 2]);
    expect(groups[0].entries.map((entry) => entry.type)).toEqual([
      "map",
      "step",
      "step",
    ]);
    expect(groups[0].entryIndexByStepId.get(2)).toBe(2);
    expect(groups[0].countryRuns).toEqual([
      {
        code: "AR",
        name: "Argentina",
        color: "#111111",
        stepIds: [1, 2],
        firstEntryIndex: 1,
        dateRange:
          "2024-01-01T00:00:00.000Z - 2024-01-02T00:00:00.000Z",
      },
    ]);
  });
});
