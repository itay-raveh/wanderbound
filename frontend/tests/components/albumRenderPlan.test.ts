import type { AlbumChapter } from "@/client";
import {
  buildEditorItems,
  buildPhysicalRenderItems,
  type ChapterRenderGroup,
} from "@/components/album/albumRenderPlan";
import { makeStep } from "../helpers";

const chapter: AlbumChapter = {
  id: "chapter-1",
  title: "Chapter",
  subtitle: "",
  front_cover_photo: "front.jpg",
  back_cover_photo: "back.jpg",
};

function group(
  steps: ReturnType<typeof makeStep>[],
  headerKeys: ChapterRenderGroup["headerKeys"] = [],
): ChapterRenderGroup {
  return {
    chapter,
    headerKeys,
    steps,
    segments: [],
    sections: steps.map((step) => ({ type: "step", step })),
  };
}

describe("album render planning", () => {
  test("keeps a spread as one editor item and two adjacent print pages", () => {
    const step = makeStep({
      pages: [{ kind: "panorama_spread", media: ["wide.jpg"] }],
    });

    const editorItems = buildEditorItems([group([step])], new Map());
    const physicalTypes = buildPhysicalRenderItems(editorItems).map(
      (item) => item.type,
    );

    expect(
      editorItems.filter((item) => item.type === "panorama-spread"),
    ).toHaveLength(1);
    expect(physicalTypes).toEqual([
      "step-page",
      "panorama-spread-left",
      "panorama-spread-right",
    ]);
  });

  test("inserts one alignment page when a spread would start on a right page", () => {
    const step = makeStep({
      pages: [{ kind: "panorama_spread", media: ["wide.jpg"] }],
    });

    const editorItems = buildEditorItems(
      [group([step], ["overview"])],
      new Map(),
    );

    expect(editorItems.map((item) => item.type)).toEqual([
      "header",
      "step-page",
      "alignment",
      "panorama-spread",
    ]);
  });

  test("recalculates later spread parity from the reordered complete sequence", () => {
    const simple = makeStep({ id: 1 });
    const firstSpread = makeStep({
      id: 2,
      pages: [{ kind: "panorama_spread", media: ["first.jpg"] }],
    });
    const laterSpread = makeStep({
      id: 3,
      pages: [{ kind: "panorama_spread", media: ["later.jpg"] }],
    });

    const original = buildEditorItems(
      [group([firstSpread, simple, laterSpread])],
      new Map(),
    );
    const reordered = buildEditorItems(
      [group([simple, firstSpread, laterSpread])],
      new Map(),
    );

    expect(
      original.filter((item) => item.type === "alignment"),
    ).toHaveLength(0);
    expect(
      reordered.filter((item) => item.type === "alignment").map((item) => item.step.id),
    ).toEqual([2, 3]);
  });

  test("restarts spread parity for each chapter", () => {
    const firstChapterStep = makeStep({ id: 1 });
    const secondChapterSpread = makeStep({
      id: 2,
      pages: [{ kind: "panorama_spread", media: ["wide.jpg"] }],
    });
    const secondChapter = {
      ...group([secondChapterSpread]),
      chapter: { ...chapter, id: "chapter-2" },
    };

    const editorItems = buildEditorItems(
      [group([firstChapterStep]), secondChapter],
      new Map(),
    );

    expect(editorItems.filter((item) => item.type === "alignment")).toEqual([]);
  });
});
