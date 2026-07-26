import type { StepRead as Step } from "@/client";
import type { StepMutationUpdate } from "@/queries/useStepMutation";
import { useDragState } from "./useDragState";
import { usePrintMode } from "./usePrintReady";
import { inject, provide, ref, watch, type InjectionKey, type Ref } from "vue";
import { useDraggable } from "vue-draggable-plus";

type StepMutateFn = (payload: {
  sid: number;
  update: StepMutationUpdate;
}) => void;

const STEP_MUTATE_KEY: InjectionKey<StepMutateFn> = Symbol("step-mutate");

/** Remove a set of photos from all pages and unused list of a step. */
function stripPhotos(step: Step, photoSet: Set<string>) {
  return {
    pages: step.pages
      .map((page) => ({
        ...page,
        media: page.media.filter((name) => !photoSet.has(name)),
      }))
      .filter((page) => page.media.length > 0),
    unused: step.unused.filter((p) => !photoSet.has(p)),
  };
}

/** Compute the update payload when the cover changes. */
export function coverUpdatePayload(
  step: Step,
  newCover: string,
): StepMutationUpdate {
  const { pages, unused } = stripPhotos(step, new Set([newCover]));
  return {
    cover: newCover,
    pages,
    unused: step.cover ? [...unused, step.cover] : unused,
  };
}

/** Compute the update payload when the unused list changes (reorder, add from page). */
export function unusedUpdatePayload(
  step: Step,
  nextUnused: string[],
): StepMutationUpdate {
  const existing = new Set(step.unused);
  const added = nextUnused.filter((p) => !existing.has(p));
  if (added.length > 0) {
    return { ...stripPhotos(step, new Set(added)), unused: nextUnused };
  }
  return { unused: nextUnused };
}

export function provideStepMutate(fn: StepMutateFn) {
  provide(STEP_MUTATE_KEY, fn);
}

export function fullPageLayout(
  step: Step,
  idx: number,
  media: string,
): Step["pages"] | null {
  const target = step.pages[idx];
  if (!target || !target.media.includes(media)) return null;
  const pages = [...step.pages];
  if (target.kind === "panorama_spread") {
    pages[idx] = { kind: "grid", media: [media] };
  } else {
    if (target.media.length <= 1) return null;
    pages.splice(
      idx,
      1,
      { ...target, media: target.media.filter((name) => name !== media) },
      { kind: "grid", media: [media] },
    );
  }
  return pages;
}

interface DropRefs {
  dropZoneRef: Ref<HTMLElement | null>;
  coverDropRef: Ref<HTMLElement | null>;
}

/**
 * Manages step photo layout: drag-and-drop between pages, cover, and unused tray.
 * Caller provides template refs for the drop zones so vue-tsc tracks their usage.
 */
export function useStepLayout(
  step: Ref<Step>,
  { dropZoneRef, coverDropRef }: DropRefs,
) {
  const printMode = usePrintMode();
  const isDragging = useDragState();
  const mutate = inject(STEP_MUTATE_KEY, null);

  const dropZoneList = ref<string[]>([]);
  const coverDropList = ref<string[]>([]);

  function saveField(patch: StepMutationUpdate) {
    mutate?.({ sid: step.value.id, update: patch });
  }

  function withoutPhotos(photoSet: Set<string>) {
    return stripPhotos(step.value, photoSet);
  }

  function onCoverUpdate(cover: string) {
    saveField(coverUpdatePayload(step.value, cover));
  }

  function onPageUpdate(idx: number, media: string[]) {
    const s = step.value;
    const target = s.pages[idx];
    if (!target || (target.kind === "panorama_spread" && media.length !== 1))
      return;

    const existing = new Set(target.media);
    const added = media.filter((name) => !existing.has(name));

    if (added.length > 0) {
      // Cross-list move: replace target page in-place, strip dragged photos
      // from all other pages atomically (can't use withoutPhotos + splice
      // because filtering empty pages shifts indices).
      const addedSet = new Set(added);
      const pages = s.pages
        .map((p, i) =>
          i === idx
            ? { ...p, media }
            : {
                ...p,
                media: p.media.filter((name) => !addedSet.has(name)),
              },
        )
        .filter((p) => p.media.length > 0);
      const unused = s.unused.filter((p) => !addedSet.has(p));
      saveField({ pages, unused });
    } else {
      const pages = [...s.pages];
      pages[idx] = { ...target, media };
      saveField({ pages });
    }
  }

  function onUnusedUpdate(unused: string[]) {
    saveField(unusedUpdatePayload(step.value, unused));
  }

  function onMakeFullPage(idx: number, media: string) {
    const pages = fullPageLayout(step.value, idx, media);
    if (!pages) return;
    saveField({ pages });
  }

  function onMakePanoramaSpread(idx: number, media: string) {
    const target = step.value.pages[idx];
    if (
      !target ||
      target.kind !== "grid" ||
      target.media.length !== 1 ||
      target.media[0] !== media
    )
      return;
    const pages = [...step.value.pages];
    pages[idx] = { kind: "panorama_spread", media: [media] };
    saveField({ pages });
  }

  if (!printMode) {
    // dropZoneRef is null when totalPhotos < 2 (v-if hides the element).
    // Defer SortableJS init until the element actually exists.
    const dropDraggable = useDraggable(dropZoneRef, dropZoneList, {
      group: "photos",
      animation: 200,
      immediate: false,
      onAdd: () => {
        if (dropZoneList.value.length === 0) return;
        const photos = [...dropZoneList.value];
        dropZoneList.value = [];
        const cleaned = withoutPhotos(new Set(photos));
        saveField({
          ...cleaned,
          pages: [...cleaned.pages, { kind: "grid", media: photos }],
        });
      },
    });
    watch(dropZoneRef, (el) => {
      if (el) dropDraggable.start(el);
    });

    const coverDraggable = useDraggable(coverDropRef, coverDropList, {
      group: "photos",
      animation: 200,
      immediate: false,
      onAdd: () => {
        if (coverDropList.value.length === 0) return;
        const photo = coverDropList.value[0];
        coverDropList.value = [];
        onCoverUpdate(photo);
      },
    });
    watch(coverDropRef, (el) => {
      if (el) coverDraggable.start(el);
    });
  }

  return {
    printMode,
    isDragging,
    saveField,
    onPageUpdate,
    onMakeFullPage,
    onMakePanoramaSpread,
    onUnusedUpdate,
    onCoverUpdate,
  };
}
