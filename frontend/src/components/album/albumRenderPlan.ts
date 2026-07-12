import type {
  AlbumChapter,
  AlbumMedia,
  AlbumMeta,
  SegmentOutline,
  StepRead as Step,
} from "@/client";
import { layoutDescription } from "@/composables/useTextLayout";
import { isPortrait } from "@/utils/media";
import {
  buildSections,
  chapterHeaderSectionKey,
  filterCoverFromPages,
  sectionKey,
  sectionPageCount,
  segmentsOverlapping,
  type HeaderKey,
  type Section,
} from "./albumSections";
import { mapRangesForSteps, stepsForChapter } from "./albumChapters";

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

function stepHasPhotoDropZone(step: Step): boolean {
  return (
    step.pages.reduce((n, page) => n + page.length, 0) + step.unused.length >= 2
  );
}

function stepEditorPagePhotoIds(
  step: Step,
  mediaByName: ReadonlyMap<string, AlbumMedia>,
): string[][] {
  const rawPhotoPages = filterCoverFromPages(step.pages, step.cover);
  const continuationPages = layoutDescription(
    step.description || "",
  ).pages.slice(1);
  const continuationPhotos: string[] = [];
  for (const { page } of rawPhotoPages) {
    for (const name of page) {
      const media = mediaByName.get(name);
      if (media && isPortrait(media)) continuationPhotos.push(name);
      if (continuationPhotos.length >= continuationPages.length) break;
    }
    if (continuationPhotos.length >= continuationPages.length) break;
  }

  const used = new Set(continuationPhotos);
  const photoPages = used.size
    ? rawPhotoPages
        .map(({ page }) => page.filter((p) => !used.has(p)))
        .filter((page) => page.length > 0)
    : rawPhotoPages.map(({ page }) => page);

  return [
    [],
    ...continuationPages.map((_, i) =>
      continuationPhotos[i] ? [continuationPhotos[i]] : [],
    ),
    ...photoPages,
  ];
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
      const stepPages = stepEditorPagePhotoIds(section.step, mediaByName);
      for (let pageIndex = 0; pageIndex < stepPages.length; pageIndex++) {
        result.push({
          type: "step-page",
          key: `${sectionKey(section)}-page-${pageIndex}`,
          step: section.step,
          pageIndex,
          photoIds: stepPages[pageIndex] ?? [],
        });
      }
      if (stepHasPhotoDropZone(section.step)) {
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
