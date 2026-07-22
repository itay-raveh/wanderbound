<script lang="ts" setup>
import type {
  AlbumMedia,
  AlbumMeta,
  SegmentOutline,
  StepRead as Step,
} from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { providePrintMode } from "@/composables/usePrintReady";
import { provideStepMutate } from "@/composables/useStepLayout";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useStepMutation } from "@/queries/useStepMutation";
import { editorZoom, setEditorZoom } from "@/composables/useEditorZoom";
import { DEFAULT_BODY_FONT, DEFAULT_FONT, fontStack } from "@/utils/fonts";
import { daysBetween, parseLocalDate } from "@/utils/date";
import { PAGE_HEIGHT_MM, MM_PX } from "@/utils/pageSize";
import {
  DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  summarizeQuality,
} from "@/utils/photoQuality";
import { setSafeMargin } from "@/composables/useSafeMargin";
import { setQualitySummary } from "@/composables/usePhotoQuality";
import { visibleHeaderKeys, sectionKey } from "./album/albumSections";
import {
  buildChapterRenderGroups,
  buildEditorItems,
  countChapterRenderPages,
  type ChapterRenderGroup,
} from "./album/albumRenderPlan";
import { useActiveSection, pickBestItem } from "@/composables/useActiveSection";
import { useWindowVirtualizer } from "@/composables/useWindowVirtualizer";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";
import {
  computed,
  defineAsyncComponent,
  defineComponent,
  h,
  nextTick,
  onMounted,
  onUnmounted,
  provide,
  readonly,
  ref,
  watchEffect,
} from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const EmptyPage = defineComponent({
  render: () => h("div", { class: "page-container" }),
});

const MapPage = defineAsyncComponent({
  loader: () => import("./album/map/MapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const HikeMapPage = defineAsyncComponent({
  loader: () => import("./album/map/HikeMapPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const OverviewPage = defineAsyncComponent({
  loader: () => import("./album/overview/OverviewPage.vue"),
  errorComponent: EmptyPage,
  timeout: 10_000,
});
const props = defineProps<{
  album: AlbumMeta;
  media: AlbumMedia[];
  steps: Step[];
  segmentOutlines: SegmentOutline[];
  printMode?: boolean;
}>();

const albumId = computed(() => props.album.id);
const albumColors = computed(
  () => (props.album.colors ?? {}) as Record<string, string>,
);
const albumMedia = computed(() => props.media);

const safeMarginMm = computed(() => props.album.safe_margin_mm ?? 0);
watchEffect(() => setSafeMargin(safeMarginMm.value));

const albumStyle = computed(() => {
  const sm = safeMarginMm.value;
  return {
    "--font-album": fontStack(props.album.font ?? DEFAULT_FONT),
    "--font-album-body": fontStack(props.album.body_font ?? DEFAULT_BODY_FONT),
    "--safe-margin": `${sm}mm`,
    ...(sm > 0
      ? {
          "--page-inset-x": `max(3rem, ${sm}mm)`,
          "--page-inset-y": `max(2.5rem, ${sm}mm)`,
        }
      : {}),
  };
});
const albumMutation = useAlbumMutation(() => props.album.id);

const visibleSteps = computed(() => {
  const hidden = new Set(props.album.hidden_steps ?? []);
  if (!hidden.size) return props.steps;
  return props.steps.filter((s) => !hidden.has(s.id));
});

const tripStart = computed(() => visibleSteps.value[0]?.datetime ?? "");
const totalDays = computed(() => {
  const s = visibleSteps.value;
  if (s.length < 2) return 1;
  const first = parseLocalDate(s[0].datetime);
  const last = parseLocalDate(s[s.length - 1].datetime);
  return Math.max(1, daysBetween(first, last) + 1);
});
const mediaResolutionWarningPreset = computed(
  () =>
    props.album.media_resolution_warning_preset ??
    DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
);
const { mediaByName } = provideAlbum({
  albumId,
  colors: albumColors,
  media: albumMedia,
  tripStart,
  totalDays,
  mediaResolutionWarningPreset,
});

const activeHeaders = computed(() =>
  visibleHeaderKeys(props.album.hidden_headers ?? []),
);

const chapterRenderGroups = computed<ChapterRenderGroup[]>(() =>
  buildChapterRenderGroups(
    props.album,
    visibleSteps.value,
    props.segmentOutlines,
    activeHeaders.value,
  ),
);

if (!props.printMode) {
  watchEffect(() => {
    const summary = { caution: 0, warning: 0 };
    for (const group of chapterRenderGroups.value) {
      const chapterSummary = summarizeQuality(
        group.steps,
        group.chapter.front_cover_photo,
        group.chapter.back_cover_photo,
        mediaByName.value,
        mediaResolutionWarningPreset.value,
      );
      summary.caution += chapterSummary.caution;
      summary.warning += chapterSummary.warning;
    }
    setQualitySummary(summary);
  });
}

const expectedPageCount = computed(
  () => countChapterRenderPages(chapterRenderGroups.value, mediaByName.value),
);
const listRef = ref<HTMLElement | null>(null);
const pageContentSuspended = ref(false);
const scrollMargin = ref(0);
const scrollPaddingStart = ref(0);
const NAV_SCROLL_MIN_TOP_CLEARANCE = 48;
const NAV_SCROLL_MAX_TOP_CLEARANCE = 88;
const NAV_SCROLL_VIEWPORT_CLEARANCE_RATIO = 0.1;

const pageH = computed(
  () => Math.round(PAGE_HEIGHT_MM * MM_PX * editorZoom.value) + 12,
);
const editorPhotoDropZoneHeight = 96;

const editorItems = computed(() =>
  buildEditorItems(chapterRenderGroups.value, mediaByName.value),
);

const { virtualizer, items, size, version } = useWindowVirtualizer(
  computed(() => {
    return {
      count: editorItems.value.length,
      estimateSize: (index: number) => {
        return editorItems.value[index]?.type === "step-add-zone"
          ? editorPhotoDropZoneHeight
          : pageH.value;
      },
      overscan: 3,
      gap: 16,
      scrollMargin: scrollMargin.value,
      scrollPaddingStart: scrollPaddingStart.value,
      getItemKey: (index: number) => editorItems.value[index]?.key ?? index,
    };
  }),
);

function sectionIdAt(vIndex: number) {
  const item = editorItems.value[vIndex];
  if (!item) return null;
  if (item.type === "header") return item.key;
  if (item.type === "step-page" || item.type === "step-add-zone")
    return item.step.id;
  return item.key;
}

function onWheel(e: WheelEvent) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
  setEditorZoom(editorZoom.value - px * 0.001);
}

if (props.printMode) {
  providePrintMode();
} else {
  const stepMut = useStepMutation(() => props.album.id);
  provideStepMutate((payload) => stepMut.mutate(payload));

  const undoStack = useUndoStack();
  undoStack.registerMutators(
    (sid, update) => stepMut.mutate({ sid, update }),
    (update) => albumMutation.mutate(update),
  );

  const {
    setScrollOverride,
    setActive,
    scrollBehavior: getScrollBehavior,
    programmaticScrolling,
  } = useActiveSection();

  // Suppress photo fetches in steps the smooth scroll passes through.
  // MediaItem injects this and skips src/srcset while it's true.
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

  function onCancelKey(e: KeyboardEvent) {
    if (
      e.key === "PageUp" ||
      e.key === "PageDown" ||
      e.key === "Home" ||
      e.key === "End" ||
      e.key === "ArrowUp" ||
      e.key === "ArrowDown" ||
      e.key === " "
    ) {
      clearProgrammaticScroll();
    }
  }

  const stepIdToVIdx = computed(() => {
    const map = new Map<number, number>();
    editorItems.value.forEach((item, i) => {
      if (item.type === "step-page" && item.pageIndex === 0) {
        map.set(item.step.id, i);
      }
    });
    return map;
  });
  const photoIdToVIdx = computed(() => {
    const map = new Map<string, number>();
    editorItems.value.forEach((item, i) => {
      if (item.type !== "step-page") return;
      for (const photoId of item.photoIds) {
        map.set(`${item.step.id}\0${photoId}`, i);
      }
    });
    return map;
  });
  const secKeyToVIdx = computed(() => {
    const map = new Map<string, number>();
    editorItems.value.forEach((item, i) => {
      if (
        item.type === "header" ||
        item.type === "map" ||
        item.type === "hike"
      ) {
        map.set(item.key, i);
      }
    });
    return map;
  });

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

  function correctScrollTarget(idx: number) {
    function applyCorrection() {
      const pageEl = listRef.value?.querySelector<HTMLElement>(
        `[data-index="${idx}"] .page-container`,
      );
      const headerBottom =
        document
          .querySelector<HTMLElement>(".editor-header")
          ?.getBoundingClientRect().bottom ?? 0;
      if (!pageEl || headerBottom <= 0) return;
      const hiddenBy =
        headerBottom +
        navScrollTopClearance(headerBottom) -
        pageEl.getBoundingClientRect().top;
      if (Math.abs(hiddenBy) > 1)
        window.scrollBy({ top: -hiddenBy, behavior: "instant" });
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

  async function jumpToDistantItem(idx: number, top: number) {
    const jumpId = ++distantJumpId;
    // Firefox can lock while a far window jump replaces heavyweight virtual pages.
    // Keep the fixed-height shells mounted until the new range has settled.
    pageContentSuspended.value = true;
    await nextTick();
    if (jumpId !== distantJumpId) return;

    window.scrollTo({ top, behavior: "instant" });
    requestAnimationFrame(() => {
      if (jumpId !== distantJumpId) return;
      pageContentSuspended.value = false;
      correctScrollTarget(idx);
    });
  }

  function scrollToVIdx(
    idx: number,
    behavior?: ScrollBehavior,
    correctForHeader = false,
  ) {
    const b =
      behavior ?? (getScrollBehavior() === "smooth" ? "smooth" : "auto");
    if (correctForHeader) {
      const v = virtualizer as unknown as {
        scrollState: null;
        getMeasurements: () => Array<{ start: number }>;
      };
      v.scrollState = null;
      const item = v.getMeasurements()[idx];
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
          void jumpToDistantItem(idx, top);
          return;
        }
        window.scrollTo({ top, behavior: "instant" });
      } else {
        virtualizer.scrollToIndex(idx, {
          align: "start",
          behavior: "instant",
        });
      }
      correctScrollTarget(idx);
      return;
    }
    if (b === "smooth") {
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
    virtualizer.scrollToIndex(idx, { align: "start", behavior: b });
  }

  function scrollToStep(
    id: number,
    behavior?: ScrollBehavior,
    correctForHeader = false,
  ) {
    const idx = stepIdToVIdx.value.get(id);
    if (idx != null) scrollToVIdx(idx, behavior, correctForHeader);
  }

  function scrollToPhoto(
    stepId: number,
    photoId: string,
    behavior: ScrollBehavior = "auto",
  ) {
    const idx = photoIdToVIdx.value.get(`${stepId}\0${photoId}`);
    if (idx != null) {
      scrollToVIdx(idx, behavior);
      return;
    }
    scrollToStep(stepId, behavior);
  }

  setScrollOverride({
    scrollTo(id: number) {
      scrollToStep(id, undefined, true);
    },
    scrollToSection(key: string): boolean {
      const idx = secKeyToVIdx.value.get(key);
      if (idx == null) return false;
      scrollToVIdx(idx, undefined, true);
      return true;
    },
  });

  const photoFocus = usePhotoFocus();
  photoFocus.init({
    steps: () => visibleSteps.value,
    mutate: (sid, update, focus) => stepMut.mutate({ sid, update, focus }),
    scrollToPhoto,
  });
  onUnmounted(() => photoFocus.dispose());

  watchEffect(() => {
    void version.value; // subscribe to every scroll tick
    if (programmaticScrolling.value) return;
    const vItems = items.value;
    if (!vItems.length) {
      setActive(null);
      return;
    }

    const best = pickBestItem(
      vItems,
      window.scrollY,
      scrollMargin.value,
      window.innerHeight / 2,
    );
    setActive(best ? (sectionIdAt(best.index) ?? null) : null);
  });

  onMounted(() => {
    if (listRef.value) {
      scrollMargin.value = Math.round(
        listRef.value.getBoundingClientRect().top + window.scrollY,
      );
      const headerBottom =
        document
          .querySelector<HTMLElement>(".editor-header")
          ?.getBoundingClientRect().bottom ?? 0;
      scrollPaddingStart.value = Math.round(headerBottom + scrollMargin.value);
    }
  });
  onUnmounted(() => {
    disposed = true;
    distantJumpId++;
    setScrollOverride(null);
    clearProgrammaticScroll();
  });
}
</script>

<template>
  <!-- Print mode: everything in normal document flow for page breaks -->
  <div
    v-if="printMode && visibleSteps.length"
    class="album-container print-mode"
    :data-expected-pages="expectedPageCount"
    :style="albumStyle"
  >
    <template v-for="group in chapterRenderGroups" :key="group.chapter.id">
      <CoverPage
        v-if="group.headerKeys.includes('cover-front')"
        :album="album"
        :chapter="group.chapter"
        :steps="group.steps"
      />
      <CoverPage
        v-if="group.headerKeys.includes('cover-back')"
        :album="album"
        :chapter="group.chapter"
        :steps="group.steps"
        is-back
      />
      <OverviewPage
        v-if="group.headerKeys.includes('overview')"
        :album="album"
        :segments="group.segments"
        :steps="group.steps"
      />
      <div v-if="group.headerKeys.includes('full-map')" class="map-wrapper">
        <MapPage :segment-outlines="group.segments" :steps="group.steps" />
      </div>

      <template v-for="section in group.sections" :key="sectionKey(section)">
        <template v-if="section.type === 'map' || section.type === 'hike'">
          <div class="map-wrapper">
            <MapPage
              v-if="section.type === 'map'"
              :segment-outlines="section.segments"
              :steps="section.steps"
            />
            <HikeMapPage
              v-else
              :segments="section.segments"
              :steps="section.steps"
              :hike-segment="section.hikeSegment"
              :all-segments="segmentOutlines"
            />
          </div>
        </template>
        <StepEntry v-else :step="section.step" />
      </template>
    </template>
  </div>

  <!-- Editor mode: virtual scrolling - only visible sections are in the DOM -->
  <div
    v-else-if="visibleSteps.length"
    :class="['album-container', { 'has-safe-margin': safeMarginMm > 0 }]"
    :data-expected-pages="expectedPageCount"
    :style="[{ '--editor-zoom': String(editorZoom) }, albumStyle]"
    @wheel="onWheel"
  >
    <div
      ref="listRef"
      :style="{
        height: `${size}px`,
        position: 'relative',
        overflowAnchor: 'none',
      }"
    >
      <div
        :style="{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          transform: `translateY(${(items[0]?.start ?? 0) - scrollMargin}px)`,
        }"
      >
        <div
          v-for="vItem in items"
          :key="vItem.key as PropertyKey"
          :data-index="vItem.index"
          :style="{ minHeight: `${vItem.size}px` }"
        >
          <template v-if="!pageContentSuspended && editorItems[vItem.index]">
            <template
              v-for="item in [editorItems[vItem.index]!]"
              :key="item.key"
            >
            <CoverPage
              v-if="item.type === 'header' && item.headerKey === 'cover-front'"
              :album="album"
              :chapter="item.chapter"
              :steps="item.steps"
            />
            <CoverPage
              v-else-if="item.type === 'header' && item.headerKey === 'cover-back'"
              :album="album"
              :chapter="item.chapter"
              :steps="item.steps"
              is-back
            />
            <OverviewPage
              v-else-if="item.type === 'header' && item.headerKey === 'overview'"
              :album="album"
              :segments="item.segments"
              :steps="item.steps"
            />
            <div
              v-else-if="item.type === 'header' && item.headerKey === 'full-map'"
              class="map-wrapper"
            >
              <MapPage :segment-outlines="item.segments" :steps="item.steps" />
            </div>
            <div v-else-if="item.type === 'map'" class="map-wrapper">
              <MapPage
                :segment-outlines="item.section.segments"
                :steps="item.section.steps"
              />
            </div>
            <div v-else-if="item.type === 'hike'" class="map-wrapper">
              <HikeMapPage
                :segments="item.section.segments"
                :steps="item.section.steps"
                :hike-segment="item.section.hikeSegment"
                :all-segments="segmentOutlines"
              />
            </div>
            <StepEntry
              v-else-if="item.type === 'step-page'"
              :step="item.step"
              :page-index="item.pageIndex"
            />
            <StepEntry
              v-else-if="item.type === 'step-add-zone'"
              :step="item.step"
              add-zone-only
            />
            </template>
          </template>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="fit relative-position">
    <q-inner-loading
      :label="t('album.loading', { name: album.chapters?.[0]?.title || album.id })"
      showing
    />
  </div>
</template>

<style lang="scss" scoped>
// :deep needed because page-containers live inside child components
:deep(.page-container) {
  width: var(--page-width);
  height: var(--page-height);
  background-color: var(--page-bg, var(--bg));
  font-family: var(--font-album);
  contain: strict; // strict containment creates a positioning context for ::after
}

// Editor mode: zoom shrinks pages for preview.
// Map pages use a wrapper + transform: scale (zoom breaks Mapbox canvas sizing).
.album-container:not(.print-mode) {
  padding: var(--gap-md-lg);
  overflow-x: auto;

  :deep(.page-container) {
    zoom: var(--editor-zoom);
    border: 3px dashed color-mix(in srgb, var(--text) 25%, transparent);
    margin: 0 auto var(--gap-md-lg);

    &.drag-over {
      border-color: var(--q-primary);
    }
  }

  // Safe margin frame - editor-only visual guide
  &.has-safe-margin :deep(.page-container)::after {
    content: "";
    position: absolute;
    inset: var(--safe-margin);
    border: 1px dashed color-mix(in srgb, var(--text) 40%, transparent);
    pointer-events: none;
    z-index: 50;
  }

  // Map wrapper: fixed layout size matching zoomed page dimensions
  .map-wrapper {
    position: relative;
    width: calc(var(--page-width) * var(--editor-zoom));
    height: calc(var(--page-height) * var(--editor-zoom));
    margin: 0 auto var(--gap-md-lg);
    overflow: hidden;

    // Inner page-container: full A4, scaled to fit wrapper.
    // Absolute positioning + rtl:ignore pins it to top-left regardless
    // of document direction (RTL block flow would anchor it to the right).
    :deep(.page-container) {
      zoom: 1;
      margin: 0;
      transform: scale(var(--editor-zoom));
      content-visibility: visible;
      /* rtl:begin:ignore */
      position: absolute;
      left: 0;
      top: 0;
      transform-origin: top left;
      /* rtl:end:ignore */
    }
  }
}

// Print mode: override contain:strict from base rule - size containment
// prevents intrinsic sizing that break-after/page relies on.
.album-container.print-mode :deep(.page-container) {
  contain: none;
  overflow: hidden;
  break-after: page;
  break-inside: avoid;
  box-sizing: border-box;
}

.album-container.print-mode :deep(.mapboxgl-ctrl-logo) {
  display: none;
}

.album-container.print-mode .map-wrapper {
  width: auto;
  height: auto;
  overflow: visible;
  border: none;
  margin: 0;

  :deep(.page-container) {
    transform: none;
  }
}

@media print {
  .album-container {
    padding: 0;
  }

  :deep(.page-container) {
    break-after: always;
    break-inside: avoid;
    margin: 0;
  }

  .map-wrapper {
    width: auto !important;
    height: auto !important;
    overflow: visible !important;
    border: none !important;
    margin: 0 !important;

    :deep(.page-container) {
      transform: none !important;
    }
  }
}
</style>
