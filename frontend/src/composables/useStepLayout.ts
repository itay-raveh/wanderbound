import type { Step, StepUpdate } from "@/client";
import { useDragState } from "./useDragState";
import { usePrintMode } from "./usePrintReady";
import { inject, provide, ref, watch, type InjectionKey, type Ref } from "vue";
import { useDraggable } from "vue-draggable-plus";

type StepMutateFn = (payload: { sid: number; update: StepUpdate }) => void;

const STEP_MUTATE_KEY: InjectionKey<StepMutateFn> = Symbol("step-mutate");

/** Remove a set of photos from all pages and unused list of a step. */
export function stripPhotos(step: Step, photoSet: Set<string>) {
  return {
    pages: step.pages
      .map((page) => page.filter((p) => !photoSet.has(p)))
      .filter((page) => page.length > 0),
    unused: step.unused.filter((p) => !photoSet.has(p)),
  };
}

/** Compute the update payload when the unused list changes (reorder, add from page). */
export function unusedUpdatePayload(step: Step, nextUnused: string[]): Partial<StepUpdate> {
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

interface DropRefs {
  dropZoneRef: Ref<HTMLElement | null>;
  coverDropRef: Ref<HTMLElement | null>;
}

/**
 * Manages step photo layout: drag-and-drop between pages, cover, and unused tray.
 * Caller provides template refs for the drop zones so vue-tsc tracks their usage.
 */
export function useStepLayout(step: Ref<Step>, { dropZoneRef, coverDropRef }: DropRefs) {
  const printMode = usePrintMode();
  const isDragging = useDragState();
  const mutate = inject(STEP_MUTATE_KEY, null);

  const dropZoneList = ref<string[]>([]);
  const coverDropList = ref<string[]>([]);

  function saveField(patch: Partial<StepUpdate>) {
    mutate?.({ sid: step.value.id, update: patch });
  }

  function withoutPhotos(photoSet: Set<string>) {
    return stripPhotos(step.value, photoSet);
  }

  function onCoverUpdate(cover: string) {
    const oldCover = step.value.cover;
    const { pages, unused } = withoutPhotos(new Set([cover]));
    saveField({
      cover,
      pages,
      unused: oldCover ? [...unused, oldCover] : unused,
    });
  }

  function onPageUpdate(idx: number, page: string[]) {
    const s = step.value;
    const existing = new Set(s.pages[idx]);
    const added = page.filter((p) => !existing.has(p));

    if (added.length > 0) {
      // Cross-list move: replace target page in-place, strip dragged photos
      // from all other pages atomically (can't use withoutPhotos + splice
      // because filtering empty pages shifts indices).
      const addedSet = new Set(added);
      const pages = s.pages
        .map((p, i) =>
          i === idx ? page : p.filter((photo) => !addedSet.has(photo)),
        )
        .filter((p) => p.length > 0);
      const unused = s.unused.filter((p) => !addedSet.has(p));
      saveField({ pages, unused });
    } else {
      const pages = [...s.pages];
      pages[idx] = page;
      saveField({ pages });
    }
  }

  function onUnusedUpdate(unused: string[]) {
    saveField(unusedUpdatePayload(step.value, unused));
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
        saveField({ ...cleaned, pages: [...cleaned.pages, photos] });
      },
    });
    watch(dropZoneRef, (el) => { if (el) dropDraggable.start(el); });

    useDraggable(coverDropRef, coverDropList, {
      group: "photos",
      animation: 200,
      onAdd: () => {
        if (coverDropList.value.length === 0) return;
        const photo = coverDropList.value[0]!;
        coverDropList.value = [];
        onCoverUpdate(photo);
      },
    });
  }

  return {
    printMode,
    isDragging,
    saveField,
    onPageUpdate,
    onUnusedUpdate,
    onCoverUpdate,
  };
}
