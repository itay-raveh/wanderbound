import type {
  AlbumMedia,
  StepPageLayoutOutput,
  StepRead as Step,
  StepSlotLayout,
} from "@/client";
import { layoutDescription, type TextPage } from "@/composables/useTextLayout";
import { isPortrait } from "@/utils/media";

interface IndexedPage {
  originalIdx: number;
  page: StepPageLayoutOutput;
}

export function pageSlots(page: StepPageLayoutOutput): StepSlotLayout[] {
  return page.slots;
}

export function withSlots(
  page: StepPageLayoutOutput,
  slots: StepSlotLayout[],
): StepPageLayoutOutput {
  return {
    ...page,
    slots,
    media: slots.flatMap((slot) =>
      slot.kind === "photo" && slot.media_name ? [slot.media_name] : [],
    ),
  };
}

export function photoSlot(name: string): StepSlotLayout {
  return { id: crypto.randomUUID(), kind: "photo", media_name: name };
}

export function gridPage(slots: StepSlotLayout[]): StepPageLayoutOutput {
  return withSlots(
    { id: crypto.randomUUID(), kind: "grid", media: [], slots: [] },
    slots,
  );
}

type PlannedStepPage =
  | { kind: "step"; photoIds: string[] }
  | {
      kind: StepPageLayoutOutput["kind"];
      photoIds: string[];
      originalIdx: number;
      page: StepPageLayoutOutput;
    };

type StepPagePlan = {
  sidebarText: TextPage | undefined;
  continuationPages: TextPage[];
  continuationPhotos: string[];
  tilePages: IndexedPage[];
  editorPages: PlannedStepPage[];
  totalPhotos: number;
  hasPhotoDropZone: boolean;
  sourcePages: StepPageLayoutOutput[];
};

export function reorderStepTilePages(
  plan: StepPagePlan,
  from: number,
  to: number,
): StepPageLayoutOutput[] | null {
  if (from === to || !plan.tilePages[from] || !plan.tilePages[to]) return null;
  const pages = [...plan.sourcePages];
  const indices = plan.tilePages.map(({ originalIdx }) => originalIdx);
  const visible = indices.map((index) => pages[index]);
  const [moved] = visible.splice(from, 1);
  visible.splice(to, 0, moved);
  indices.forEach((index, position) => {
    pages[index] = visible[position]!;
  });
  return pages;
}

export function filterCoverFromPages(
  pages: StepPageLayoutOutput[],
  cover: string | null | undefined,
): IndexedPage[] {
  if (!cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({
      originalIdx: i,
      page: withSlots(
        page,
        pageSlots(page).filter((slot) => slot.media_name !== cover),
      ),
    }))
    .filter(({ page }) => pageSlots(page).length > 0);
}

function selectContinuationPhotos(
  tilePages: IndexedPage[],
  mediaByName: ReadonlyMap<string, AlbumMedia>,
  needed: number,
): string[] {
  if (needed === 0) return [];
  const result: string[] = [];
  const candidates = tilePages
    .filter(({ page }) => page.kind === "grid")
    .flatMap(({ page }) => pageSlots(page))
    .filter((slot) => slot.kind === "photo" && slot.media_name)
    .sort(
      (a, b) =>
        (a.continuation_priority ?? Infinity) -
        (b.continuation_priority ?? Infinity),
    );
  for (const slot of candidates) {
    const name = slot.media_name!;
    const media = mediaByName.get(name);
    if (media && isPortrait(media)) result.push(name);
    if (result.length >= needed) return result;
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
  const tilePages = used.size
    ? rawPhotoPages
        .map(({ originalIdx, page }) => ({
          originalIdx,
          page: withSlots(
            page,
            pageSlots(page).filter(
              (slot) =>
                slot.kind === "text" || !used.has(slot.media_name ?? ""),
            ),
          ),
        }))
        .filter(({ page }) => pageSlots(page).length > 0)
    : rawPhotoPages;
  const totalPhotos =
    step.pages.reduce((n, page) => n + page.media.length, 0) +
    step.unused.length;
  const totalTextTiles = step.pages.reduce(
    (count, page) =>
      count + pageSlots(page).filter((slot) => slot.kind === "text").length,
    0,
  );

  return {
    sidebarText: descriptionPages[0],
    continuationPages,
    continuationPhotos,
    tilePages,
    editorPages: [
      { kind: "step", photoIds: [] },
      ...continuationPages.map((_, i) => ({
        kind: "step" as const,
        photoIds: continuationPhotos[i] ? [continuationPhotos[i]] : [],
      })),
      ...tilePages.map(({ originalIdx, page }) => ({
        kind: page.kind,
        photoIds: page.media,
        originalIdx,
        page,
      })),
    ],
    totalPhotos,
    hasPhotoDropZone: totalPhotos + totalTextTiles >= 2,
    sourcePages: step.pages,
  };
}
