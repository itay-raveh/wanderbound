<script lang="ts" setup>
import type { Album, AlbumData } from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import LazySection from "./LazySection.vue";
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
import { vSpyStep } from "@/composables/useStepScrollSpy";
import { computed, defineAsyncComponent, defineComponent, h } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const editorZoom = `${EDITOR_ZOOM}`;

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

// In print mode, provide a flag so child components can set loading="eager".
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
}
</script>

<template>
  <div
    v-if="steps.length"
    :class="['album-container', { 'print-mode': printMode }]"
    :data-expected-pages="expectedPageCount"
  >
    <CoverPage :album="album" :steps="steps" />
    <CoverPage :album="album" :steps="steps" is-back />
    <OverviewPage :album="album" :segments="segments" :steps="steps" />

    <!-- Not user-editable: always covers the full trip -->
    <div class="map-wrapper">
      <MapPage :segments="segments" :steps="steps" />
    </div>

    <template v-for="(section, i) in sections" :key="sectionKey(section)">
      <LazySection
        :data-section-key="sectionKey(section)"
        :page-count="sectionPageCounts[i]"
        :has-chrome="section.type === 'step'"
        v-spy-step="section.type === 'step' ? section.step.id : sectionKey(section)"
      >
        <!-- Map / Hike section with shared controls -->
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
      </LazySection>
    </template>
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
  --editor-zoom: v-bind(editorZoom);
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

  :deep(.lazy-section),
  :deep(.lazy-placeholder) {
    margin-top: var(--gap-lg);
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
