<script lang="ts" setup>
import type { Album, AlbumData, Segment, Step } from "@/client";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import LazySection from "./LazySection.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { providePrintMode } from "@/composables/usePrintReady";
import { PAGE_CHARS } from "@/composables/usePageDescription";
import { EDITOR_ZOOM } from "@/utils/media";
import { toRangeList } from "@/utils/ranges";
import { computed, defineAsyncComponent, defineComponent, h } from "vue";

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

/** Number of album pages a section will render (for lazy placeholder sizing). */
function sectionPageCount(section: Section): number {
  if (section.type === "map" || section.type === "hike") return 1;
  const step = section.step;
  const descLen = (step.description || "").length;
  let pages = 1 + step.pages.length;
  if (descLen > PAGE_CHARS) pages += Math.ceil((descLen - PAGE_CHARS) / PAGE_CHARS);
  return pages;
}


function segmentsOverlapping(segs: Segment[], tStart: number, tEnd: number): Segment[] {
  return segs.filter((seg) => seg.start_time <= tEnd && seg.end_time >= tStart);
}


const props = defineProps<{
  album: Album;
  data: AlbumData;
  printMode?: boolean;
}>();

const albumId = computed(() => props.album.id);
const albumColors = computed(() => (props.album.colors ?? {}) as Record<string, string>);
const albumOrientations = computed(() => (props.album.orientations ?? {}) as Record<string, string>);

// Filter steps/segments by the album's steps_ranges setting.
const stepsIndexes = computed(() => {
  const ranges = toRangeList(props.album.steps_ranges);
  const set = new Set<number>();
  for (const r of ranges) {
    for (let i = r.start; i <= r.end; i++) set.add(i);
  }
  return set;
});

const steps = computed(() =>
  props.data.steps.filter((s) => stepsIndexes.value.has(s.idx)),
);

const segments = computed(() => {
  const s = steps.value;
  if (s.length === 0) return [];
  return segmentsOverlapping(props.data.segments, s[0]!.timestamp, s[s.length - 1]!.timestamp);
});

const tripStart = computed(() => steps.value[0]?.datetime ?? "");
const totalDays = computed(() => {
  const s = steps.value;
  if (s.length < 2) return 1;
  const first = new Date(s[0]!.datetime);
  const last = new Date(s[s.length - 1]!.datetime);
  first.setHours(0, 0, 0, 0);
  last.setHours(0, 0, 0, 0);
  return Math.max(1, Math.floor((last.getTime() - first.getTime()) / 86_400_000) + 1);
});
provideAlbum({ albumId, colors: albumColors, orientations: albumOrientations, tripStart, totalDays });

type Section =
  | { type: "map"; steps: Step[]; segments: Segment[] }
  | { type: "hike"; steps: Step[]; segments: Segment[]; hikeSegment: Segment }
  | { type: "step"; step: Step };

const sections = computed<Section[]>(() => {
  const allSteps = steps.value;
  const allSegments = segments.value;

  const mapsRangeStr = props.album.maps_ranges;
  const mapRanges = mapsRangeStr ? toRangeList(mapsRangeStr) : [];

  type MapEntry = {
    start: number;
    end: number;
    steps: Step[];
    segments: Segment[];
  };
  const mapEntries: MapEntry[] = mapRanges.map((r) => {
    const rangeSteps = allSteps.filter(
      (s) => s.idx >= r.start && s.idx <= r.end,
    );
    const rangeStart = rangeSteps[0]?.timestamp;
    const rangeEnd = rangeSteps[rangeSteps.length - 1]?.timestamp;
    const rangeSegments =
      rangeStart == null || rangeEnd == null
        ? []
        : segmentsOverlapping(allSegments, rangeStart, rangeEnd);
    return {
      start: r.start,
      end: r.end,
      steps: rangeSteps,
      segments: rangeSegments,
    };
  });

  const result: Section[] = [];
  const mapInsertionPoints = new Map<number, MapEntry[]>();
  for (const entry of mapEntries) {
    if (entry.steps.length === 0) continue;
    const firstIdx = entry.steps[0]!.idx;
    if (!mapInsertionPoints.has(firstIdx)) {
      mapInsertionPoints.set(firstIdx, []);
    }
    mapInsertionPoints.get(firstIdx)!.push(entry);
  }

  for (const step of allSteps) {
    const maps = mapInsertionPoints.get(step.idx);
    if (maps) {
      for (const m of maps) {
        const hikeSegment = m.segments.find((s) => s.kind === "hike");
        if (hikeSegment) {
          result.push({
            type: "hike",
            steps: m.steps,
            segments: m.segments,
            hikeSegment,
          });
        } else {
          result.push({ type: "map", steps: m.steps, segments: m.segments });
        }
      }
    }
    result.push({ type: "step", step });
  }

  if (mapRanges.length === 0 && allSegments.length > 0) {
    result.unshift({ type: "map", steps: allSteps, segments: allSegments });
  }

  return result;
});

/** Total page-container count: covers (2) + overview (1) + sections. */
const expectedPageCount = computed(() =>
  3 + sections.value.reduce((n, s) => n + sectionPageCount(s), 0),
);

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

    <LazySection
      v-for="(section, i) in sections"
      :key="i"
      :page-count="sectionPageCount(section)"
      :has-chrome="section.type === 'step'"
      :eager="section.type === 'map' || section.type === 'hike'"
    >
      <!-- Map pages wrapped so transform: scale doesn't misalign -->
      <div v-if="section.type === 'map'" class="map-wrapper">
        <MapPage
          :segments="section.segments"
          :steps="section.steps"
        />
      </div>
      <div v-else-if="section.type === 'hike'" class="map-wrapper">
        <HikeMapPage
          :segments="section.segments"
          :steps="section.steps"
          :hike-segment="section.hikeSegment"
        />
      </div>
      <StepEntry
        v-else-if="section.type === 'step'"
        :step="section.step"
      />
    </LazySection>
  </div>
  <div v-else class="fit relative-position">
    <q-inner-loading
      :label="`Loading '${album.title || album.id}'...`"
      showing
    />
  </div>
</template>

<style lang="scss" scoped>
// :deep needed because page-containers live inside child components
:deep(.page-container) {
  width: 297mm;
  height: 210mm;
  background-color: var(--page-bg, var(--bg));
  contain: content;
}

// Editor mode: zoom shrinks pages for preview.
// Map pages use a wrapper + transform: scale (zoom breaks Mapbox canvas sizing).
.album-container:not(.print-mode) {
  --editor-zoom: v-bind(editorZoom);
  padding: 0.75rem;

  :deep(.page-container) {
    zoom: var(--editor-zoom);
    border: 2px dashed color-mix(in srgb, var(--text) 25%, transparent);
    margin: 0 auto 0.75rem;

    &.drag-over {
      border-color: var(--q-primary);
    }
  }

  // Map wrapper: fixed layout size matching zoomed page dimensions
  .map-wrapper {
    width: calc(297mm * var(--editor-zoom));
    height: calc(210mm * var(--editor-zoom));
    margin: 0 auto 0.75rem;
    overflow: hidden;
    border: 2px dashed color-mix(in srgb, var(--text) 25%, transparent);

    // Inner page-container: full A4, scaled to fit wrapper
    :deep(.page-container) {
      zoom: 1;
      border: none;
      margin: 0;
      transform: scale(var(--editor-zoom));
      transform-origin: top left;
    }
  }
}

// Print mode: exact A4 sizing, no editor chrome.
// contain:content is removed (inherited from base rule) because it creates
// an isolated formatting context that can cause sub-pixel clipping at edges.
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
}
</style>
