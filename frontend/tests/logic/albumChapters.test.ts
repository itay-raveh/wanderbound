import {
  applyStepRange,
  mapRangesForSteps,
  stepOptionsForChapter,
  stepsForChapter,
  unassignedSteps,
} from "@/components/album/albumChapters";
import type { AlbumChapter } from "@/client";
import { makeStep } from "../helpers";

const steps = [
  makeStep({ id: 1, name: "One" }),
  makeStep({ id: 2, name: "Two" }),
  makeStep({ id: 3, name: "Three" }),
  makeStep({ id: 4, name: "Four" }),
];

const chapters: AlbumChapter[] = [
  {
    id: "first",
    title: "First",
    subtitle: null,
    step_ids: [2, 1],
    front_cover_photo: "front.jpg",
    back_cover_photo: "back.jpg",
  },
  {
    id: "second",
    title: "Second",
    subtitle: null,
    step_ids: [4],
    front_cover_photo: "front.jpg",
    back_cover_photo: "back.jpg",
  },
];

describe("album chapter logic", () => {
  it("selects chapter steps in album order", () => {
    expect(stepsForChapter(steps, chapters[0]).map((step) => step.id)).toEqual([
      1, 2,
    ]);
  });

  it("returns unassigned steps", () => {
    expect(unassignedSteps(steps, chapters).map((step) => step.id)).toEqual([
      3,
    ]);
  });

  it("filters map ranges to ranges containing visible steps", () => {
    const datedSteps = [
      makeStep({ id: 1, datetime: "2024-01-10T00:00:00Z" }),
      makeStep({ id: 2, datetime: "2024-02-10T00:00:00Z" }),
    ];

    expect(
      mapRangesForSteps(
        [
          ["2024-01-01", "2024-01-31"],
          ["2024-03-01", "2024-03-31"],
        ],
        datedSteps,
      ),
    ).toEqual([["2024-01-01", "2024-01-31"]]);
  });

  it("disables steps assigned to other chapters", () => {
    expect(stepOptionsForChapter(steps, chapters, chapters[0])).toEqual([
      { label: "One", value: 1, disable: false },
      { label: "Two", value: 2, disable: false },
      { label: "Three", value: 3, disable: false },
      { label: "Four", value: 4, disable: true },
    ]);
  });

  it("applies ranges while excluding steps assigned elsewhere", () => {
    expect(applyStepRange(steps, chapters, chapters[0], 1, 4)).toEqual([
      1, 2, 3,
    ]);
  });
});
