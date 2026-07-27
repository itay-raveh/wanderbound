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
  | {
      type: "grid";
      key: string;
      step: Step;
      pageIndex: number;
      originalPageIndex: number;
      page: Step["pages"][number];
      photoIds: string[];
    }
  | {
      type: "panorama-spread";
      key: string;
      step: Step;
      pageIndex: number;
      originalPageIndex: number;
      media: string;
      photoIds: string[];
    }
  | {
      type: "alignment";
      key: string;
      step: Step;
    }
  | { type: "step-add-zone"; key: string; step: Step };

export type PhysicalRenderItem =
  | Exclude<EditorItem, { type: "step-add-zone" | "panorama-spread" }>
  | {
      type: "panorama-spread-left" | "panorama-spread-right";
      key: string;
      step: Step;
      media: string;
    };

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

export function buildEditorItems(
  groups: ChapterRenderGroup[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
): EditorItem[] {
  const result: EditorItem[] = [];
  groups.forEach((group) => {
    let physicalPageCount = 0;
    for (const headerKey of group.headerKeys) {
      result.push({
        type: "header" as const,
        key: chapterHeaderSectionKey(group.chapter.id, headerKey),
        headerKey,
        chapter: group.chapter,
        steps: group.steps,
        segments: group.segments,
      });
      physicalPageCount++;
    }
    group.sections.forEach((section) => {
      if (section.type === "map") {
        result.push({ type: "map", key: sectionKey(section), section });
        physicalPageCount++;
        return;
      }
      if (section.type === "hike") {
        result.push({ type: "hike", key: sectionKey(section), section });
        physicalPageCount++;
        return;
      }
      const stepPlan = planStepPages(section.step, mediaByName);
      const stepPages = stepPlan.editorPages;
      for (let pageIndex = 0; pageIndex < stepPages.length; pageIndex++) {
        const page = stepPages[pageIndex];
        if (!page) continue;
        const key = `${sectionKey(section)}-page-${pageIndex}`;
        if (page.kind === "step") {
          result.push({
            type: "step-page",
            key,
            step: section.step,
            pageIndex,
            photoIds: page.photoIds,
          });
          physicalPageCount++;
          continue;
        }
        if (page.kind === "grid") {
          result.push({
            type: "grid",
            key,
            step: section.step,
            pageIndex,
            originalPageIndex: page.originalIdx,
            page: page.page,
            photoIds: page.photoIds,
          });
          physicalPageCount++;
          continue;
        }
        if (physicalPageCount % 2 === 0) {
          result.push({
            type: "alignment",
            key: `${key}-alignment`,
            step: section.step,
          });
          physicalPageCount++;
        }
        result.push({
          type: "panorama-spread",
          key,
          step: section.step,
          pageIndex,
          originalPageIndex: page.originalIdx,
          media: page.photoIds[0],
          photoIds: page.photoIds,
        });
        physicalPageCount += 2;
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

export function buildPhysicalRenderItems(
  editorItems: EditorItem[],
): PhysicalRenderItem[] {
  return editorItems.flatMap((item): PhysicalRenderItem[] => {
    if (item.type === "step-add-zone") return [];
    if (item.type !== "panorama-spread") return [item];
    return [
      {
        type: "panorama-spread-left",
        key: `${item.key}-left`,
        step: item.step,
        media: item.media,
      },
      {
        type: "panorama-spread-right",
        key: `${item.key}-right`,
        step: item.step,
        media: item.media,
      },
    ];
  });
}
