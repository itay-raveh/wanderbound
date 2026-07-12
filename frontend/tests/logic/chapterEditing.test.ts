import {
  adjustChapterBoundary,
  deleteChapter,
  splitChapter,
} from "@/components/editor/nav/chapterEditing";
import { makeStep } from "../helpers";
import type { AlbumChapter } from "@/client";

function chapter(
  overrides: Partial<AlbumChapter> & Pick<AlbumChapter, "id" | "step_ids">,
): AlbumChapter {
  return {
    title: "",
    subtitle: "",
    front_cover_photo: "",
    back_cover_photo: "",
    ...overrides,
  };
}

describe("chapterEditing", () => {
  it("splits a chapter into two valid chapters", () => {
    const chapters = [
      chapter({
        id: "chapter-1",
        title: "South",
        step_ids: [1, 2, 3, 4],
        front_cover_photo: "old.jpg",
        back_cover_photo: "old.jpg",
      }),
    ];
    const steps = [
      makeStep({ id: 1 }),
      makeStep({ id: 2 }),
      makeStep({ id: 3, cover: "three.jpg" }),
      makeStep({ id: 4 }),
    ];

    expect(splitChapter(chapters, steps, "chapter-1")).toEqual([
      {
        ...chapters[0],
        step_ids: [1, 2],
      },
      {
        id: "chapter-2",
        title: "",
        subtitle: "",
        step_ids: [3, 4],
        front_cover_photo: "three.jpg",
        back_cover_photo: "three.jpg",
      },
    ]);
  });

  it("adjusts the boundary between adjacent chapters", () => {
    const chapters = [
      chapter({ id: "chapter-1", step_ids: [1, 2] }),
      chapter({ id: "chapter-2", step_ids: [3, 4] }),
    ];

    expect(adjustChapterBoundary(chapters, "chapter-1", "chapter-2", 2)).toEqual([
      chapter({ id: "chapter-1", step_ids: [1] }),
      chapter({ id: "chapter-2", step_ids: [2, 3, 4] }),
    ]);
  });

  it("merges a deleted chapter into its previous neighbor", () => {
    const chapters = [
      chapter({ id: "chapter-1", step_ids: [1] }),
      chapter({ id: "chapter-2", step_ids: [2, 3] }),
      chapter({ id: "chapter-3", step_ids: [4] }),
    ];

    expect(deleteChapter(chapters, "chapter-2")).toEqual([
      chapter({ id: "chapter-1", step_ids: [1, 2, 3] }),
      chapter({ id: "chapter-3", step_ids: [4] }),
    ]);
  });

});
