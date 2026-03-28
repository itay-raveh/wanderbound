<script lang="ts" setup>
import type { Album, AlbumData } from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { providePrintMode } from "@/composables/usePrintReady";
import { provideStepMutate } from "@/composables/useStepLayout";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useStepMutation } from "@/queries/useStepMutation";
import { EDITOR_ZOOM } from "@/utils/media";
import { daysBetween, isoDate, inDateRange, parseLocalDate } from "@/utils/date";
import { buildSections, sectionKey, sectionPageCount, segmentsOverlapping } from "./album/albumSections";
import { vSpyStep, useStepScrollSpy } from "@/composables/useStepScrollSpy";
import { useWindowVirtualizer } from "@/composables/useWindowVirtualizer";
import { computed, defineAsyncComponent, defineComponent, h, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

// Fallback for async components that fail to load (e.g. mapbox-gl in headless Chromium).
// Renders an empty page-container so page count stays correct and a blank page appears in the PDF.
const EmptyPage = defineComponent({
  render: () => h("div", { class: "page-container" }),
});

// Async components - splits turf/mapbox-gl out of the main chunk.
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
  album: Album;
  data: AlbumData;
  printMode?: boolean;
}>();

const albumId = computed(() => props.album.id);
const albumColors = computed(() => (props.album.colors ?? {}) as Record<string, string>);
const albumMedia = computed(() => (props.album.media ?? {}) as Record<string, string>);
const albumMutation = useAlbumMutation(() => props.album.id);

const steps = computed(() => {
  const ranges = props.album.steps_ranges;
  if (!ranges?.length) return props.data.steps;
  return props.data.steps.filter((s) => {
    const d = isoDate(s.datetime);
    return ranges.some((r) => inDateRange(d, r));
  });
});

const segments = computed(() => {
  const s = steps.value;
  if (s.length === 0) return [];
  return segmentsOverlapping(props.data.segments, s[0]!.timestamp, s[s.length - 1]!.timestamp);
});

const tripStart = computed(() => steps.value[0]?.datetime ?? "");
const totalDays = computed(() => {
  const s = steps.value;
  if (s.length < 2) return 1;
  const first = parseLocalDate(s[0]!.datetime);
  const last = parseLocalDate(s[s.length - 1]!.datetime);
  return Math.max(1, daysBetween(first, last) + 1);
});
provideAlbum({ albumId, colors: albumColors, media: albumMedia, tripStart, totalDays });

const sections = computed(() =>
  buildSections(steps.value, segments.value, props.album.maps_ranges ?? []),
);

const sectionPageCounts = computed(() => sections.value.map(sectionPageCount));

/** Total page-container count: covers (2) + overview (1) + full-trip map (1) + sections. */
const expectedPageCount = computed(() =>
  4 + sectionPageCounts.value.reduce((n, c) => n + c, 0),
);

// ---------------------------------------------------------------------------
// Virtual scroller — only active in editor mode
// ---------------------------------------------------------------------------
const HEADER_COUNT = 4; // front cover, back cover, overview, full-trip map
const listRef = ref<HTMLElement | null>(null);
const itemEls = ref<HTMLElement[]>([]);
const scrollMargin = ref(0);

// Estimated height of one A4 page at editor zoom: 210mm → px at 96 DPI, scaled, plus gap.
const PAGE_H = Math.round(210 * 96 / 25.4 * EDITOR_ZOOM) + 12;

const { virtualizer, items, size } = useWindowVirtualizer(computed(() => ({
  count: HEADER_COUNT + sections.value.length,
  estimateSize: (index: number) => {
    if (index < HEADER_COUNT) return PAGE_H;
    return (sectionPageCounts.value[index - HEADER_COUNT] ?? 1) * PAGE_H;
  },
  overscan: 3,
  gap: 16,
  scrollMargin: scrollMargin.value,
  getItemKey: (index: number) => {
    if (index === 0) return "cover-front";
    if (index === 1) return "cover-back";
    if (index === 2) return "overview";
    if (index === 3) return "full-map";
    const sec = sections.value[index - HEADER_COUNT];
    return sec ? sectionKey(sec) : index;
  },
})));

/** Map virtual-item index → scroll-spy value (step id | section key | undefined). */
function spyValue(vIndex: number): number | string | undefined {
  if (vIndex < HEADER_COUNT) return undefined;
  const sec = sections.value[vIndex - HEADER_COUNT];
  if (!sec) return undefined;
  return sec.type === "step" ? sec.step.id : sectionKey(sec);
}

function measureAll() {
  virtualizer.measureElement(null);
  for (const el of itemEls.value) {
    if (el) virtualizer.measureElement(el);
  }
}

// ---------------------------------------------------------------------------
// Mode-specific setup
// ---------------------------------------------------------------------------
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

  const photoFocus = usePhotoFocus();
  photoFocus.setStepOrder(() => steps.value.map((s) => s.id));

  // Wire scroll-spy navigation through the virtualizer so clicking a nav
  // item scrolls even when the target section is off-screen (not in the DOM).
  const { setScrollOverride, scrollBehavior: getScrollBehavior } = useStepScrollSpy();

  const stepIdToVIdx = computed(() => {
    const map = new Map<number, number>();
    sections.value.forEach((s, i) => {
      if (s.type === "step") map.set(s.step.id, HEADER_COUNT + i);
    });
    return map;
  });
  const secKeyToVIdx = computed(() => {
    const map = new Map<string, number>();
    sections.value.forEach((s, i) => map.set(sectionKey(s), HEADER_COUNT + i));
    return map;
  });

  function scrollToVIdx(idx: number) {
    virtualizer.scrollToIndex(idx, {
      align: "start",
      behavior: getScrollBehavior() === "smooth" ? "smooth" : "auto",
    });
  }

  setScrollOverride({
    scrollTo(id: number) {
      const idx = stepIdToVIdx.value.get(id);
      if (idx != null) scrollToVIdx(idx);
    },
    scrollToSection(key: string): boolean {
      const idx = secKeyToVIdx.value.get(key);
      if (idx == null) return false;
      scrollToVIdx(idx);
      return true;
    },
  });

  onMounted(() => {
    if (listRef.value) {
      scrollMargin.value = Math.round(listRef.value.getBoundingClientRect().top + window.scrollY);
    }
    measureAll();
  });
  watch(items, measureAll);
  onUnmounted(() => {
    setScrollOverride(null);
  });
}
</script>

<template>
  <!-- Print mode: everything in normal document flow for page breaks -->
  <div
    v-if="printMode && steps.length"
    class="album-container print-mode"
    :data-expected-pages="expectedPageCount"
  >
    <CoverPage :album="album" :steps="steps" />
    <CoverPage :album="album" :steps="steps" is-back />
    <OverviewPage :album="album" :segments="segments" :steps="steps" />
    <div class="map-wrapper"><MapPage :segments="segments" :steps="steps" /></div>

    <template v-for="section in sections" :key="sectionKey(section)">
      <template v-if="section.type === 'map' || section.type === 'hike'">
        <div class="map-wrapper">
          <MapPage v-if="section.type === 'map'" :segments="section.segments" :steps="section.steps" />
          <HikeMapPage
            v-else
            :segments="section.segments"
            :steps="section.steps"
            :hike-segment="section.hikeSegment"
            :all-segments="data.segments"
          />
        </div>
      </template>
      <StepEntry v-else :step="section.step" />
    </template>
  </div>

  <!-- Editor mode: virtual scrolling — only visible sections are in the DOM -->
  <div
    v-else-if="steps.length"
    class="album-container"
    :data-expected-pages="expectedPageCount"
    :style="{ '--editor-zoom': String(EDITOR_ZOOM) }"
  >
    <div ref="listRef" :style="{ height: `${size}px`, position: 'relative' }">
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
          ref="itemEls"
          v-spy-step="spyValue(vItem.index)"
        >
          <!-- Header items -->
          <CoverPage v-if="vItem.index === 0" :album="album" :steps="steps" />
          <CoverPage v-else-if="vItem.index === 1" :album="album" :steps="steps" is-back />
          <OverviewPage v-else-if="vItem.index === 2" :album="album" :segments="segments" :steps="steps" />
          <div v-else-if="vItem.index === 3" class="map-wrapper">
            <MapPage :segments="segments" :steps="steps" />
          </div>

          <!-- Section items -->
          <template v-else>
            <div
              v-if="sections[vItem.index - HEADER_COUNT]?.type !== 'step'"
              class="map-wrapper"
            >
              <MapPage
                v-if="sections[vItem.index - HEADER_COUNT]?.type === 'map'"
                :segments="(sections[vItem.index - HEADER_COUNT] as any).segments"
                :steps="(sections[vItem.index - HEADER_COUNT] as any).steps"
              />
              <HikeMapPage
                v-else
                :segments="(sections[vItem.index - HEADER_COUNT] as any).segments"
                :steps="(sections[vItem.index - HEADER_COUNT] as any).steps"
                :hike-segment="(sections[vItem.index - HEADER_COUNT] as any).hikeSegment"
                :all-segments="data.segments"
              />
            </div>
            <StepEntry v-else :step="(sections[vItem.index - HEADER_COUNT] as any).step" />
          </template>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="fit relative-position">
    <q-inner-loading
      :label="t('album.loading', { name: album.title || album.id })"
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
  contain: strict;
}

// Editor mode: zoom shrinks pages for preview.
// Map pages use a wrapper + transform: scale (zoom breaks Mapbox canvas sizing).
.album-container:not(.print-mode) {
  padding: var(--gap-md-lg);

  :deep(.page-container) {
    zoom: var(--editor-zoom);
    border: 3px dashed color-mix(in srgb, var(--text) 25%, transparent);
    margin: 0 auto var(--gap-md-lg);
    content-visibility: auto;
    contain-intrinsic-height: auto var(--page-height);

    &.drag-over {
      border-color: var(--q-primary);
    }
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
