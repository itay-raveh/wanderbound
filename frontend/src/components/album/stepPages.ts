import type {
  AlbumMedia,
  StepPageLayout,
  StepRead as Step,
} from "@/client";
import {
  layoutDescription,
  type JustifiedLine,
} from "@/composables/useTextLayout";
import { isPortrait } from "@/utils/media";

export interface IndexedPage {
  originalIdx: number;
  page: StepPageLayout;
}

type PlannedStepPage =
  | { kind: "step"; photoIds: string[] }
  | {
      kind: StepPageLayout["kind"];
      photoIds: string[];
      originalIdx: number;
      page: StepPageLayout;
    };

export type StepPagePlan = {
  sidebarLines: JustifiedLine[];
  continuationPages: JustifiedLine[][];
  continuationPhotos: string[];
  photoPages: IndexedPage[];
  editorPages: PlannedStepPage[];
  totalPhotos: number;
  hasPhotoDropZone: boolean;
};

export function filterCoverFromPages(
  pages: StepPageLayout[],
  cover: string | null | undefined,
): IndexedPage[] {
  if (!cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({
      originalIdx: i,
      page: { ...page, media: page.media.filter((name) => name !== cover) },
    }))
    .filter(({ page }) => page.media.length > 0);
}

function selectContinuationPhotos(
  photoPages: IndexedPage[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
  needed: number,
): string[] {
  if (needed === 0) return [];
  const result: string[] = [];
  for (const { page } of photoPages) {
    if (page.kind !== "grid") continue;
    for (const name of page.media) {
      const media = mediaByName.get(name);
      if (media && isPortrait(media)) result.push(name);
      if (result.length >= needed) return result;
    }
  }
  return result;
}

export function planStepPages(
  step: Step,
  mediaByName: ReadonlyMap<string, AlbumMedia>,
  descriptionPages = layoutDescription(step.description || "").pages,
): StepPagePlan {
  const rawPhotoPages = filterCoverFromPages(step.pages, step.cover);
  const continuationPages = descriptionPages.slice(1);
  const continuationPhotos = selectContinuationPhotos(
    rawPhotoPages,
    mediaByName,
    continuationPages.length,
  );
  const used = new Set(continuationPhotos);
  const photoPages = used.size
    ? rawPhotoPages
        .map(({ originalIdx, page }) => ({
          originalIdx,
          page: {
            ...page,
            media: page.media.filter((name) => !used.has(name)),
          },
        }))
        .filter(({ page }) => page.media.length > 0)
    : rawPhotoPages;
  const totalPhotos =
    step.pages.reduce((n, page) => n + page.media.length, 0) +
    step.unused.length;

  return {
    sidebarLines: descriptionPages[0] ?? [],
    continuationPages,
    continuationPhotos,
    photoPages,
    editorPages: [
      { kind: "step", photoIds: [] },
      ...continuationPages.map((_, i) => ({
        kind: "step" as const,
        photoIds: continuationPhotos[i] ? [continuationPhotos[i]] : [],
      })),
      ...photoPages.map(({ originalIdx, page }) => ({
        kind: page.kind,
        photoIds: page.media,
        originalIdx,
        page,
      })),
    ],
    totalPhotos,
    hasPhotoDropZone: totalPhotos >= 2,
  };
}
