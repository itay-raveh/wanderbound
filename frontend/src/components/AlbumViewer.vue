<script lang="ts" setup>
import type { Album, AlbumData, DateRange, Step } from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import LazySection from "./LazySection.vue";
import MapSectionControls from "./album/map/MapSectionControls.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { providePrintMode } from "@/composables/usePrintReady";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { EDITOR_ZOOM } from "@/utils/media";
import { daysBetween, isoDate, inDateRange, parseLocalDate } from "@/utils/date";
import { buildSections, sectionKey, sectionPageCount, segmentsOverlapping } from "./album/albumSections";
import { symOutlinedMap } from "@quasar/extras/material-symbols-outlined";
import { computed, defineAsyncComponent, defineComponent, h } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const editorZoom = `${EDITOR_ZOOM}`;

// Fallback for async components that fail to load (e.g. mapbox-gl in headless Chromium).
// Renders an empty page-container so page count stays correct and a blank page appears in the PDF.
const EmptyPage = defineComponent({
  render: () => h("div", { class: "page-container" }),
});

// Async components — splits turf/mapbox-gl out of the main chunk.
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
const albumOrientations = computed(() => (props.album.orientations ?? {}) as Record<string, string>);
const albumMutation = useAlbumMutation(() => props.album.id);

// Filter steps by the album's date ranges.
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
provideAlbum({ albumId, colors: albumColors, orientations: albumOrientations, tripStart, totalDays });

const sections = computed(() =>
  buildSections(steps.value, segments.value, props.album.maps_ranges ?? []),
);

const sectionPageCounts = computed(() => sections.value.map(sectionPageCount));

/** Total page-container count: covers (2) + overview (1) + sections. */
const expectedPageCount = computed(() =>
  3 + sectionPageCounts.value.reduce((n, c) => n + c, 0),
);

// --- Map range editing ---

function addMapBefore(step: Step) {
  const sd = isoDate(step.datetime);
  const ranges: DateRange[] = [...(props.album.maps_ranges ?? []), [sd, sd]];
  ranges.sort(([a], [b]) => a.localeCompare(b));
  albumMutation.mutate({ maps_ranges: ranges });
}

// In print mode, provide a flag so child components can set loading="eager".
if (props.printMode) {
  providePrintMode();
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

    <template v-for="(section, i) in sections" :key="sectionKey(section)">
      <!-- "Add map" needle before step sections without a preceding map (editor only) -->
      <div
        v-if="!printMode && section.type === 'step' && sections[i - 1]?.type !== 'map' && sections[i - 1]?.type !== 'hike'"
        class="map-needle row no-wrap items-center cursor-pointer"
        @click="addMapBefore(section.step)"
      >
        <div class="needle-line" />
        <div class="needle-head row no-wrap items-center text-weight-medium">
          <q-icon :name="symOutlinedMap" size="1rem" />
          <span>{{ t("album.addMap") }}</span>
        </div>
        <div class="needle-line" />
      </div>

      <LazySection
        :page-count="sectionPageCounts[i]"
        :has-chrome="section.type === 'step'"
        :eager="section.type === 'map' || section.type === 'hike'"
      >
        <!-- Map / Hike section with shared controls -->
        <div v-if="section.type === 'map' || section.type === 'hike'" class="map-wrapper">
          <MapSectionControls
            v-if="!printMode"
            :album-id="album.id"
            :maps-ranges="album.maps_ranges ?? []"
            :range-idx="section.rangeIdx"
            :date-range="section.dateRange"
            :steps="steps"
          />
          <MapPage v-if="section.type === 'map'" :segments="section.segments" :steps="section.steps" />
          <HikeMapPage
            v-else
            :segments="section.segments"
            :steps="section.steps"
            :hike-segment="section.hikeSegment"
          />
        </div>

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

  // Map wrapper: fixed layout size matching zoomed page dimensions
  .map-wrapper {
    position: relative;
    width: calc(var(--page-width) * var(--editor-zoom));
    height: calc(var(--page-height) * var(--editor-zoom));
    margin: 0 auto var(--gap-md-lg);
    overflow: hidden;

    // Inner page-container: full A4, scaled to fit wrapper
    :deep(.page-container) {
      zoom: 1;
      margin: 0;
      transform: scale(var(--editor-zoom));
      transform-origin: top left;
      content-visibility: visible;
    }
  }
}

// "Add map" needle between sections (editor only)
.map-needle {
  width: calc(var(--page-width) * var(--editor-zoom));
  margin: 2rem auto var(--gap-md-lg);
  color: var(--text-faint);
  overflow: visible;
  transition: color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
  }
}

.needle-head {
  flex-shrink: 0;
  gap: var(--gap-sm);
  padding: var(--gap-sm) 0.625rem;
  border-radius: var(--radius-full);
  border: 1px solid currentColor;
  white-space: nowrap;
  font-size: var(--type-xs);
}

.needle-line {
  flex: 1;
  height: 1px;
  background: currentColor;
}

// Print mode: override contain:strict from base rule — size containment
// prevents intrinsic sizing that break-after/page relies on.
.album-container.print-mode :deep(.page-container) {
  contain: none;
  overflow: hidden;
  break-after: page;
  break-inside: avoid;
  box-sizing: border-box;
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

  .map-needle {
    display: none !important;
  }
}
</style>
