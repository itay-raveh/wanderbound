import type { AlbumMedia, StepRead as Step } from "@/client";
import {
  layoutDescription,
  type JustifiedLine,
} from "@/composables/useTextLayout";
import { isPortrait } from "@/utils/media";

export interface IndexedPage {
  originalIdx: number;
  page: string[];
}

export type StepPagePlan = {
  sidebarLines: JustifiedLine[];
  continuationPages: JustifiedLine[][];
  continuationPhotos: string[];
  photoPages: IndexedPage[];
  editorPagePhotoIds: string[][];
  totalPhotos: number;
  hasPhotoDropZone: boolean;
};

export function filterCoverFromPages(
  pages: string[][],
  cover: string | null | undefined,
): IndexedPage[] {
  if (!cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({
      originalIdx: i,
      page: page.filter((p) => p !== cover),
    }))
    .filter(({ page }) => page.length > 0);
}

function selectContinuationPhotos(
  photoPages: IndexedPage[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
  needed: number,
): string[] {
  if (needed === 0) return [];
  const result: string[] = [];
  for (const { page } of photoPages) {
    for (const name of page) {
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
          page: page.filter((p) => !used.has(p)),
        }))
        .filter(({ page }) => page.length > 0)
    : rawPhotoPages;
  const totalPhotos =
    step.pages.reduce((n, page) => n + page.length, 0) + step.unused.length;

  return {
    sidebarLines: descriptionPages[0] ?? [],
    continuationPages,
    continuationPhotos,
    photoPages,
    editorPagePhotoIds: [
      [],
      ...continuationPages.map((_, i) =>
        continuationPhotos[i] ? [continuationPhotos[i]] : [],
      ),
      ...photoPages.map(({ page }) => page),
    ],
    totalPhotos,
    hasPhotoDropZone: totalPhotos >= 2,
  };
}
