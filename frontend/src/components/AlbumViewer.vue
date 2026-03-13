<script lang="ts" setup>
import type { Album, AlbumData, Segment, Step } from "@/client";
import MapPage from "./album/map/MapPage.vue";
import HikeMapPage from "./album/map/HikeMapPage.vue";
import OverviewPage from "./album/overview/OverviewPage.vue";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import { providePrintMode } from "@/composables/usePrintReady";
import { useAlbumStore } from "@/stores/useAlbumStore";
import { toRangeList } from "@/utils/ranges";
import { computed, watch } from "vue";

function segmentsOverlapping(segs: Segment[], tStart: number, tEnd: number): Segment[] {
  return segs.filter((seg) => seg.start_time <= tEnd && seg.end_time >= tStart);
}


const props = defineProps<{
  album: Album;
  data: AlbumData;
  printMode?: boolean;
}>();

const albumStore = useAlbumStore();
watch(() => props.album.id, (id) => { albumStore.albumId = id; }, { immediate: true });

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

// In print mode, provide a flag so child components can set loading="eager".
// Playwright's networkidle wait handles the rest.
if (props.printMode) {
  providePrintMode();
}

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
</script>

<template>
  <div
    v-if="steps.length"
    :class="['album-container', { 'print-mode': printMode }]"
  >
    <CoverPage :album="album" :steps="steps" />
    <CoverPage :album="album" :steps="steps" is-back />
    <OverviewPage :album="album" :segments="segments" :steps="steps" />

    <template v-for="(section, i) in sections" :key="i">
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
          :colors="(album.colors as Record<string, string>)"
        />
      </div>
      <StepEntry
        v-else-if="section.type === 'step'"
        :colors="(album.colors as Record<string, string>)"
        :step="section.step"
        :trip-start="steps[0]!.datetime"
        :print-mode="printMode"
      />
    </template>
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
}

// Editor mode: zoom shrinks pages for preview.
// Map pages use a wrapper + transform: scale (zoom breaks Mapbox canvas sizing).
.album-container:not(.print-mode) {
  --editor-zoom: 0.70;
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

// Print mode: exact A4 sizing, no editor chrome
.album-container.print-mode :deep(.page-container) {
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
