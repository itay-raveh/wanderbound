import type {
  AlbumChapter,
  AlbumMedia,
  AlbumMeta,
  SegmentOutline,
  StepRead as Step,
} from "@/client";
import {
  buildSections,
  chapterHeaderSectionKey,
  sectionKey,
  sectionPageCount,
  segmentsOverlapping,
  type HeaderKey,
  type Section,
} from "./albumSections";
import { mapRangesForSteps, stepsForChapter } from "./albumChapters";
import { planStepPages } from "./stepPages";

export type ChapterRenderGroup = {
  chapter: AlbumChapter;
  headerKeys: HeaderKey[];
  steps: Step[];
  segments: SegmentOutline[];
  sections: Section[];
};

export type EditorItem =
  | {
      type: "header";
      key: string;
      headerKey: HeaderKey;
      chapter: AlbumChapter;
      steps: Step[];
      segments: SegmentOutline[];
    }
  | { type: "map"; key: string; section: Extract<Section, { type: "map" }> }
  | { type: "hike"; key: string; section: Extract<Section, { type: "hike" }> }
  | {
      type: "step-page";
      key: string;
      step: Step;
      pageIndex: number;
      photoIds: string[];
    }
  | { type: "step-add-zone"; key: string; step: Step };

export function buildChapterRenderGroups(
  album: AlbumMeta,
  visibleSteps: Step[],
  segmentOutlines: SegmentOutline[],
  headerKeys: HeaderKey[],
): ChapterRenderGroup[] {
  return (album.chapters ?? [])
    .map((chapter) => {
      const chapterSteps = stepsForChapter(visibleSteps, chapter);
      const chapterSegments =
        chapterSteps.length === 0
          ? []
          : segmentsOverlapping(
              segmentOutlines,
              chapterSteps[0].timestamp,
              chapterSteps[chapterSteps.length - 1].timestamp,
            );
      const chapterMapRanges = mapRangesForSteps(
        album.maps_ranges ?? [],
        chapterSteps,
      );
      return {
        chapter,
        headerKeys,
        steps: chapterSteps,
        segments: chapterSegments,
        sections: buildSections(
          chapterSteps,
          chapterSegments,
          chapterMapRanges,
          chapter,
        ),
      };
    })
    .filter((group) => group.steps.length > 0);
}

export function countChapterRenderPages(
  groups: ChapterRenderGroup[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
): number {
  return groups.reduce(
    (total, group) =>
      total +
      group.headerKeys.length +
      group.sections.reduce(
        (sum, section) => sum + sectionPageCount(section, mediaByName),
        0,
      ),
    0,
  );
}

export function buildEditorItems(
  groups: ChapterRenderGroup[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
): EditorItem[] {
  const result: EditorItem[] = [];
  groups.forEach((group) => {
    result.push(
      ...group.headerKeys.map((headerKey) => ({
        type: "header" as const,
        key: chapterHeaderSectionKey(group.chapter.id, headerKey),
        headerKey,
        chapter: group.chapter,
        steps: group.steps,
        segments: group.segments,
      })),
    );
    group.sections.forEach((section) => {
      if (section.type === "map") {
        result.push({ type: "map", key: sectionKey(section), section });
        return;
      }
      if (section.type === "hike") {
        result.push({ type: "hike", key: sectionKey(section), section });
        return;
      }
      const stepPlan = planStepPages(section.step, mediaByName);
      const stepPages = stepPlan.editorPagePhotoIds;
      for (let pageIndex = 0; pageIndex < stepPages.length; pageIndex++) {
        result.push({
          type: "step-page",
          key: `${sectionKey(section)}-page-${pageIndex}`,
          step: section.step,
          pageIndex,
          photoIds: stepPages[pageIndex] ?? [],
        });
      }
      if (stepPlan.hasPhotoDropZone) {
        result.push({
          type: "step-add-zone",
          key: `${sectionKey(section)}-add-zone`,
          step: section.step,
        });
      }
    });
  });
  return result;
}
