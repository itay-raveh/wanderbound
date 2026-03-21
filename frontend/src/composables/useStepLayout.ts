import type { Step, StepUpdate } from "@/client";
import { useDragState } from "./useDragState";
import { usePrintMode } from "./usePrintReady";
import { useStepMutation } from "@/queries/useStepMutation";
import { ref, type Ref } from "vue";
import { useDraggable } from "vue-draggable-plus";

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
  const stepMutation = useStepMutation();

  const dropZoneList = ref<string[]>([]);
  const coverDropList = ref<string[]>([]);

  function saveField(patch: Partial<StepUpdate>) {
    stepMutation.mutate({ sid: step.value.id, update: patch });
  }

  function saveLayout(patch: Partial<StepUpdate>) {
    const s = step.value;
    stepMutation.mutate({
      sid: s.id,
      update: { cover: s.cover, pages: s.pages, unused: s.unused, ...patch },
    });
  }

  /** Remove a set of photos from all pages and unused list atomically. */
  function withoutPhotos(photoSet: Set<string>) {
    const s = step.value;
    return {
      pages: s.pages
        .map((page) => page.filter((p) => !photoSet.has(p)))
        .filter((page) => page.length > 0),
      unused: s.unused.filter((p) => !photoSet.has(p)),
    };
  }

  function onCoverUpdate(cover: string) {
    const oldCover = step.value.cover;
    const { pages, unused } = withoutPhotos(new Set([cover]));
    saveLayout({
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
      saveLayout({ pages, unused });
    } else {
      const pages = [...s.pages];
      pages[idx] = page;
      saveLayout({ pages });
    }
  }

  function onUnusedUpdate(unused: string[]) {
    const existing = new Set(step.value.unused);
    const added = unused.filter((p) => !existing.has(p));

    if (added.length > 0) {
      const cleaned = withoutPhotos(new Set(added));
      saveLayout({ ...cleaned, unused });
    } else {
      saveLayout({ unused });
    }
  }

  if (!printMode) {
    useDraggable(dropZoneRef, dropZoneList, {
      group: "photos",
      animation: 200,
      onAdd: () => {
        if (dropZoneList.value.length === 0) return;
        const photos = [...dropZoneList.value];
        dropZoneList.value = [];
        const cleaned = withoutPhotos(new Set(photos));
        saveLayout({ ...cleaned, pages: [...cleaned.pages, photos] });
      },
    });

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
  };
}
