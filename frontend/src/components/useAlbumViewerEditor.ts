import type { StepRead as Step } from "@/client";
import { useActiveSection, pickBestItem } from "@/composables/useActiveSection";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { providePrintMode } from "@/composables/usePrintReady";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";
import {
  fullPageLayout,
  provideStepMutate,
} from "@/composables/useStepLayout";
import { useUndoStack } from "@/composables/useUndoStack";
import { useWindowVirtualizer } from "@/composables/useWindowVirtualizer";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useStepMutation } from "@/queries/useStepMutation";
import type { StepIndex } from "@/utils/steps";
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  provide,
  readonly,
  ref,
  watchEffect,
  type ComponentPublicInstance,
  type ComputedRef,
} from "vue";
import type { EditorItem } from "./album/albumRenderPlan";

const PHOTO_DROP_ZONE_HEIGHT = 96;
const NAV_SCROLL_MIN_TOP_CLEARANCE = 48;
const NAV_SCROLL_MAX_TOP_CLEARANCE = 88;
const NAV_SCROLL_VIEWPORT_CLEARANCE_RATIO = 0.1;

interface AlbumViewerEditorOptions {
  albumId: ComputedRef<string>;
  editorItems: ComputedRef<EditorItem[]>;
  pageHeight: ComputedRef<number>;
  visibleSteps: ComputedRef<Step[]>;
  visibleStepIndex: ComputedRef<StepIndex>;
  printMode: boolean;
}

export function useAlbumViewerEditor({
  albumId,
  editorItems,
  pageHeight,
  visibleSteps,
  visibleStepIndex,
  printMode,
}: AlbumViewerEditorOptions) {
  const listRef = ref<HTMLElement | null>(null);
  const pageContentSuspended = ref(false);
  const scrollMargin = ref(0);
  const scrollPaddingStart = ref(0);

  const { virtualizer, items, size, version } = useWindowVirtualizer(
    computed(() => ({
      count: editorItems.value.length,
      estimateSize: (index: number) =>
        editorItems.value[index]?.type === "step-add-zone"
          ? PHOTO_DROP_ZONE_HEIGHT
          : pageHeight.value,
      overscan: 3,
      gap: 16,
      scrollMargin: scrollMargin.value,
      scrollPaddingStart: scrollPaddingStart.value,
      getItemKey: (index: number) => editorItems.value[index]?.key ?? index,
    })),
  );

  let mutateStepLayout:
    | ((payload: { sid: number; update: { pages: Step["pages"] } }) => void)
    | null = null;

  function makeFullPage(step: Step, pageIndex: number, media: string): void {
    const pages = fullPageLayout(step, pageIndex, media);
    if (pages) mutateStepLayout?.({ sid: step.id, update: { pages } });
  }

  function setListRef(element: Element | ComponentPublicInstance | null) {
    listRef.value = element instanceof HTMLElement ? element : null;
  }

  if (printMode) {
    providePrintMode();
    return {
      setListRef,
      pageContentSuspended,
      scrollMargin,
      items,
      size,
      makeFullPage,
    };
  }

  const stepMutation = useStepMutation(() => albumId.value);
  const albumMutation = useAlbumMutation(() => albumId.value);
  mutateStepLayout = (payload) => stepMutation.mutate(payload);
  provideStepMutate((payload) => stepMutation.mutate(payload));

  useUndoStack().registerMutators(
    (sid, update) => stepMutation.mutate({ sid, update }),
    (update) => albumMutation.mutate(update),
  );

  const {
    setScrollOverride,
    setActive,
    scrollBehavior: getScrollBehavior,
    programmaticScrolling,
  } = useActiveSection();
  provide(PROGRAMMATIC_SCROLL_KEY, readonly(programmaticScrolling));

  let scrollClearTimer: ReturnType<typeof setTimeout> | null = null;
  let distantJumpId = 0;
  let disposed = false;

  function clearProgrammaticScroll() {
    programmaticScrolling.value = false;
    if (scrollClearTimer) {
      clearTimeout(scrollClearTimer);
      scrollClearTimer = null;
    }
    window.removeEventListener("wheel", clearProgrammaticScroll, true);
    window.removeEventListener("touchstart", clearProgrammaticScroll, true);
    window.removeEventListener("keydown", onCancelKey, true);
  }

  function onCancelKey(event: KeyboardEvent) {
    if (
      [
        "PageUp",
        "PageDown",
        "Home",
        "End",
        "ArrowUp",
        "ArrowDown",
        " ",
      ].includes(event.key)
    ) {
      clearProgrammaticScroll();
    }
  }

  const stepIdToIndex = computed(() => {
    const result = new Map<number, number>();
    editorItems.value.forEach((item, index) => {
      if (item.type === "step-page" && item.pageIndex === 0) {
        result.set(item.step.id, index);
      }
    });
    return result;
  });
  const photoIdToIndex = computed(() => {
    const result = new Map<string, number>();
    editorItems.value.forEach((item, index) => {
      if (
        item.type !== "step-page" &&
        item.type !== "grid" &&
        item.type !== "panorama-spread"
      ) {
        return;
      }
      for (const photoId of item.photoIds) {
        result.set(`${item.step.id}\0${photoId}`, index);
      }
    });
    return result;
  });
  const sectionKeyToIndex = computed(() => {
    const result = new Map<string, number>();
    editorItems.value.forEach((item, index) => {
      if (
        item.type === "header" ||
        item.type === "map" ||
        item.type === "hike"
      ) {
        result.set(item.key, index);
      }
    });
    return result;
  });

  function sectionIdAt(index: number) {
    const item = editorItems.value[index];
    if (!item) return null;
    if (item.type === "header") return item.key;
    if (
      item.type === "step-page" ||
      item.type === "grid" ||
      item.type === "panorama-spread" ||
      item.type === "alignment" ||
      item.type === "step-add-zone"
    ) {
      return item.step.id;
    }
    return item.key;
  }

  function navScrollTopClearance(headerBottom: number) {
    const viewportBelowHeader = Math.max(0, window.innerHeight - headerBottom);
    return Math.min(
      NAV_SCROLL_MAX_TOP_CLEARANCE,
      Math.max(
        NAV_SCROLL_MIN_TOP_CLEARANCE,
        Math.round(viewportBelowHeader * NAV_SCROLL_VIEWPORT_CLEARANCE_RATIO),
      ),
    );
  }

  function correctScrollTarget(index: number) {
    function applyCorrection() {
      const page = listRef.value?.querySelector<HTMLElement>(
        `[data-index="${index}"] .page-container`,
      );
      const headerBottom =
        document
          .querySelector<HTMLElement>(".editor-header")
          ?.getBoundingClientRect().bottom ?? 0;
      if (!page || headerBottom <= 0) return;
      const hiddenBy =
        headerBottom +
        navScrollTopClearance(headerBottom) -
        page.getBoundingClientRect().top;
      if (Math.abs(hiddenBy) > 1) {
        window.scrollBy({ top: -hiddenBy, behavior: "instant" });
      }
    }
    void nextTick(() => {
      requestAnimationFrame(() => {
        if (disposed) return;
        applyCorrection();
        requestAnimationFrame(() => {
          if (disposed) return;
          applyCorrection();
          scrollClearTimer = setTimeout(clearProgrammaticScroll, 100);
        });
      });
    });
  }

  async function jumpToDistantItem(index: number, top: number) {
    const jumpId = ++distantJumpId;
    pageContentSuspended.value = true;
    await nextTick();
    if (jumpId !== distantJumpId) return;
    window.scrollTo({ top, behavior: "instant" });
    requestAnimationFrame(() => {
      if (jumpId !== distantJumpId) return;
      pageContentSuspended.value = false;
      correctScrollTarget(index);
    });
  }

  function scrollToIndex(
    index: number,
    behavior?: ScrollBehavior,
    correctForHeader = false,
  ) {
    const resolvedBehavior =
      behavior ?? (getScrollBehavior() === "smooth" ? "smooth" : "auto");
    if (correctForHeader) {
      const internalVirtualizer = virtualizer as unknown as {
        scrollState: null;
        getMeasurements: () => Array<{ start: number }>;
      };
      internalVirtualizer.scrollState = null;
      const item = internalVirtualizer.getMeasurements()[index];
      const headerBottom =
        document
          .querySelector<HTMLElement>(".editor-header")
          ?.getBoundingClientRect().bottom ?? 0;
      distantJumpId++;
      pageContentSuspended.value = false;
      programmaticScrolling.value = true;
      if (scrollClearTimer) clearTimeout(scrollClearTimer);
      scrollClearTimer = setTimeout(clearProgrammaticScroll, 800);
      if (item) {
        const top = Math.max(
          0,
          item.start - headerBottom - navScrollTopClearance(headerBottom),
        );
        if (Math.abs(top - window.scrollY) > window.innerHeight * 4) {
          void jumpToDistantItem(index, top);
          return;
        }
        window.scrollTo({ top, behavior: "instant" });
      } else {
        virtualizer.scrollToIndex(index, {
          align: "start",
          behavior: "instant",
        });
      }
      correctScrollTarget(index);
      return;
    }
    if (resolvedBehavior === "smooth") {
      programmaticScrolling.value = true;
      window.addEventListener("wheel", clearProgrammaticScroll, {
        capture: true,
        once: true,
      });
      window.addEventListener("touchstart", clearProgrammaticScroll, {
        capture: true,
        once: true,
      });
      window.addEventListener("keydown", onCancelKey, { capture: true });
      if (scrollClearTimer) clearTimeout(scrollClearTimer);
      scrollClearTimer = setTimeout(clearProgrammaticScroll, 1500);
    }
    virtualizer.scrollToIndex(index, {
      align: "start",
      behavior: resolvedBehavior,
    });
  }

  function scrollToStep(
    id: number,
    behavior?: ScrollBehavior,
    correctForHeader = false,
  ) {
    const index = stepIdToIndex.value.get(id);
    if (index != null) scrollToIndex(index, behavior, correctForHeader);
  }

  function scrollToPhoto(
    stepId: number,
    photoId: string,
    behavior: ScrollBehavior = "auto",
  ) {
    const index = photoIdToIndex.value.get(`${stepId}\0${photoId}`);
    if (index != null) scrollToIndex(index, behavior);
    else scrollToStep(stepId, behavior);
  }

  setScrollOverride({
    scrollTo: (id) => scrollToStep(id, undefined, true),
    scrollToSection(key) {
      const index = sectionKeyToIndex.value.get(key);
      if (index == null) return false;
      scrollToIndex(index, undefined, true);
      return true;
    },
  });

  const photoFocus = usePhotoFocus();
  photoFocus.init({
    steps: () => visibleSteps.value,
    stepIndex: () => visibleStepIndex.value,
    mutate: (sid, update, focus) =>
      stepMutation.mutate({ sid, update, focus }),
    scrollToPhoto,
  });
  onUnmounted(() => photoFocus.dispose());

  watchEffect(() => {
    void version.value;
    if (programmaticScrolling.value) return;
    const visibleItems = items.value;
    if (!visibleItems.length) {
      setActive(null);
      return;
    }
    const best = pickBestItem(
      visibleItems,
      window.scrollY,
      scrollMargin.value,
      window.innerHeight / 2,
    );
    setActive(best ? (sectionIdAt(best.index) ?? null) : null);
  });

  onMounted(() => {
    if (!listRef.value) return;
    scrollMargin.value = Math.round(
      listRef.value.getBoundingClientRect().top + window.scrollY,
    );
    const headerBottom =
      document
        .querySelector<HTMLElement>(".editor-header")
        ?.getBoundingClientRect().bottom ?? 0;
    scrollPaddingStart.value = Math.round(headerBottom + scrollMargin.value);
  });
  onUnmounted(() => {
    disposed = true;
    distantJumpId++;
    setScrollOverride(null);
    clearProgrammaticScroll();
  });

  return {
    setListRef,
    pageContentSuspended,
    scrollMargin,
    items,
    size,
    makeFullPage,
  };
}
