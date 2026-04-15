<script lang="ts" setup>
import type { AlbumMeta, Media, Step, SegmentOutline } from "@/client";
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
import { summarizeQuality } from "@/utils/photoQuality";
import { setSafeMargin } from "@/composables/useSafeMargin";
import { setQualitySummary } from "@/composables/usePhotoQuality";
import {
  buildSections,
  visibleHeaderKeys,
  sectionKey,
  sectionPageCount,
  segmentsOverlapping,
  activeSectionId,
} from "./album/albumSections";
import { useActiveSection, pickBestItem } from "@/composables/useActiveSection";
import { useWindowVirtualizer } from "@/composables/useWindowVirtualizer";
import {
  computed,
  defineAsyncComponent,
  defineComponent,
  h,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  watch,
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
  media: Media[];
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

const segments = computed(() => {
  const s = visibleSteps.value;
  if (s.length === 0) return [];
  return segmentsOverlapping(
    props.segmentOutlines,
    s[0].timestamp,
    s[s.length - 1].timestamp,
  );
});

const tripStart = computed(() => visibleSteps.value[0]?.datetime ?? "");
const totalDays = computed(() => {
  const s = visibleSteps.value;
  if (s.length < 2) return 1;
  const first = parseLocalDate(s[0].datetime);
  const last = parseLocalDate(s[s.length - 1].datetime);
  return Math.max(1, daysBetween(first, last) + 1);
});
const { mediaByName } = provideAlbum({
  albumId,
  colors: albumColors,
  media: albumMedia,
  tripStart,
  totalDays,
});

if (!props.printMode) {
  watchEffect(() => {
    setQualitySummary(
      summarizeQuality(
        visibleSteps.value,
        props.album.front_cover_photo,
        props.album.back_cover_photo,
        mediaByName.value,
      ),
    );
  });
}

const sections = computed(() =>
  buildSections(
    visibleSteps.value,
    segments.value,
    props.album.maps_ranges ?? [],
  ),
);

const sectionPageCounts = computed(() => sections.value.map(sectionPageCount));

const activeHeaders = computed(() =>
  visibleHeaderKeys(props.album.hidden_headers ?? []),
);
const headerCount = computed(() => activeHeaders.value.length);

const expectedPageCount = computed(
  () => headerCount.value + sectionPageCounts.value.reduce((n, c) => n + c, 0),
);
const listRef = ref<HTMLElement | null>(null);
const itemEls = ref<HTMLElement[]>([]);
let measuredEls = new WeakSet<Element>();
const scrollMargin = ref(0);

const pageH = computed(
  () => Math.round(PAGE_HEIGHT_MM * MM_PX * editorZoom.value) + 12,
);

const { virtualizer, items, size, version } = useWindowVirtualizer(
  computed(() => {
    const hc = headerCount.value;
    const headers = activeHeaders.value;
    return {
      count: hc + sections.value.length,
      estimateSize: (index: number) => {
        if (index < hc) return pageH.value;
        return (sectionPageCounts.value[index - hc] ?? 1) * pageH.value;
      },
      overscan: 3,
      gap: 16,
      scrollMargin: scrollMargin.value,
      getItemKey: (index: number) => {
        if (index < hc) return headers[index];
        const sec = sections.value[index - hc];
        return sec ? sectionKey(sec) : index;
      },
    };
  }),
);

function sectionIdAt(vIndex: number) {
  const hc = headerCount.value;
  if (vIndex < hc) return activeHeaders.value[vIndex] ?? null;
  return activeSectionId(sections.value, vIndex - hc) ?? null;
}

function measureNew() {
  for (const el of itemEls.value) {
    if (el && !measuredEls.has(el)) {
      measuredEls.add(el);
      virtualizer.measureElement(el);
    }
  }
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
  } = useActiveSection();

  const stepIdToVIdx = computed(() => {
    const hc = headerCount.value;
    const map = new Map<number, number>();
    sections.value.forEach((s, i) => {
      if (s.type === "step") map.set(s.step.id, hc + i);
    });
    return map;
  });
  const secKeyToVIdx = computed(() => {
    const hc = headerCount.value;
    const map = new Map<string, number>();
    activeHeaders.value.forEach((key, i) => map.set(key, i));
    sections.value.forEach((s, i) => map.set(sectionKey(s), hc + i));
    return map;
  });

  function scrollToVIdx(idx: number, behavior?: ScrollBehavior) {
    virtualizer.scrollToIndex(idx, {
      align: "start",
      behavior:
        behavior ?? (getScrollBehavior() === "smooth" ? "smooth" : "auto"),
    });
  }

  function scrollToStep(id: number, behavior?: ScrollBehavior) {
    const idx = stepIdToVIdx.value.get(id);
    if (idx != null) scrollToVIdx(idx, behavior);
  }

  setScrollOverride({
    scrollTo: scrollToStep,
    scrollToSection(key: string): boolean {
      const idx = secKeyToVIdx.value.get(key);
      if (idx == null) return false;
      scrollToVIdx(idx);
      return true;
    },
  });

  const photoFocus = usePhotoFocus();
  photoFocus.init({
    steps: () => visibleSteps.value,
    mutate: (sid, update) => stepMut.mutate({ sid, update }),
    scrollToStep: (id) => scrollToStep(id, "smooth"),
  });
  onUnmounted(() => photoFocus.dispose());

  watchEffect(() => {
    void version.value; // subscribe to every scroll tick
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
    }
    measureNew();
  });
  watch(items, measureNew);
  watch(editorZoom, () => {
    measuredEls = new WeakSet();
    void nextTick(measureNew);
  });
  onUnmounted(() => {
    setScrollOverride(null);
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
    <CoverPage
      v-if="activeHeaders.includes('cover-front')"
      :album="album"
      :steps="visibleSteps"
    />
    <CoverPage
      v-if="activeHeaders.includes('cover-back')"
      :album="album"
      :steps="visibleSteps"
      is-back
    />
    <OverviewPage
      v-if="activeHeaders.includes('overview')"
      :album="album"
      :segments="segments"
      :steps="visibleSteps"
    />
    <div v-if="activeHeaders.includes('full-map')" class="map-wrapper">
      <MapPage :segment-outlines="segments" :steps="visibleSteps" />
    </div>

    <template v-for="section in sections" :key="sectionKey(section)">
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
          ref="itemEls"
        >
          <!-- Header items -->
          <template v-if="vItem.index < headerCount">
            <CoverPage
              v-if="activeHeaders[vItem.index] === 'cover-front'"
              :album="album"
              :steps="visibleSteps"
            />
            <CoverPage
              v-else-if="activeHeaders[vItem.index] === 'cover-back'"
              :album="album"
              :steps="visibleSteps"
              is-back
            />
            <OverviewPage
              v-else-if="activeHeaders[vItem.index] === 'overview'"
              :album="album"
              :segments="segments"
              :steps="visibleSteps"
            />
            <div
              v-else-if="activeHeaders[vItem.index] === 'full-map'"
              class="map-wrapper"
            >
              <MapPage :segment-outlines="segments" :steps="visibleSteps" />
            </div>
          </template>

          <!-- Section items -->
          <template v-else>
            <template
              v-for="(sec, i) in [sections[vItem.index - headerCount]!]"
              :key="i"
            >
              <div v-if="sec.type !== 'step'" class="map-wrapper">
                <MapPage
                  v-if="sec.type === 'map'"
                  :segment-outlines="sec.segments"
                  :steps="sec.steps"
                />
                <HikeMapPage
                  v-else
                  :segments="sec.segments"
                  :steps="sec.steps"
                  :hike-segment="sec.hikeSegment"
                  :all-segments="segmentOutlines"
                />
              </div>
              <StepEntry v-else :step="sec.step" />
            </template>
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
    content-visibility: auto;
    contain-intrinsic-height: auto var(--page-height);

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
