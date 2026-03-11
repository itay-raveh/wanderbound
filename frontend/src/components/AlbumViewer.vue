<script lang="ts" setup>
import type { Album, Segment, Step } from "@/client";
import MapPage from "./album/map/MapPage.vue";
import HikeMapPage from "./album/map/HikeMapPage.vue";
import OverviewPage from "./album/overview/OverviewPage.vue";
import StepEntry from "./album/StepEntry.vue";
import CoverPage from "./album/CoverPage.vue";
import { providePrintMode } from "@/composables/usePrintReady";
import { useStepsQuery } from "@/queries/useStepsQuery";
import { toRangeList } from "@/utils/ranges";
import { computed } from "vue";


const props = defineProps<{
  album: Album;
  printMode?: boolean;
}>();

const albumId = computed(() => props.album.id);
const stepsRanges = computed(() => props.album.steps_ranges);
const { data } = useStepsQuery(albumId, stepsRanges);

const steps = computed(() => data.value?.steps ?? null);
const segments = computed(() => data.value?.segments ?? null);

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
  if (!steps.value || !segments.value) return [];

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
    const rangeSegments = allSegments.filter((seg) => {
      if (seg.points.length < 2 || rangeSteps.length === 0) return false;
      const segStart = seg.points[0]!.time;
      const segEnd = seg.points[seg.points.length - 1]!.time;
      const rangeStart = rangeSteps[0]!.timestamp;
      const rangeEnd = rangeSteps[rangeSteps.length - 1]!.timestamp;
      return segStart <= rangeEnd && segEnd >= rangeStart;
    });
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
        }
        result.push({ type: "map", steps: m.steps, segments: m.segments });
      }
    }
    result.push({ type: "step", step });
  }

  if (mapRanges.length === 0 && allSegments.length > 0) {
    result.unshift({ type: "map", steps: allSteps, segments: allSegments });
    const hikeSegment = allSegments.find((s) => s.kind === "hike");
    if (hikeSegment) {
      result.splice(1, 0, {
        type: "hike",
        steps: allSteps,
        segments: allSegments,
        hikeSegment,
      });
    }
  }

  return result;
});
</script>

<template>
  <div
    v-if="steps && segments"
    :class="['album-container', { 'print-mode': printMode }]"
    class="scroll-y fit"
  >
    <CoverPage :album="album" :steps="steps" />
    <CoverPage :album="album" :steps="steps" is-back />
    <OverviewPage :album="album" :segments="segments" :steps="steps" />

    <template v-for="(section, i) in sections" :key="i">
      <MapPage
        v-if="section.type === 'map'"
        :segments="section.segments"
        :steps="section.steps"
      />
      <HikeMapPage
        v-else-if="section.type === 'hike'"
        :segments="section.segments"
        :steps="section.steps"
        :hike-segment="section.hikeSegment"
      />
      <StepEntry
        v-else-if="section.type === 'step'"
        :album-id="album.id"
        :colors="(album.colors as Record<string, string>)"
        :step="section.step"
        :steps-ranges="album.steps_ranges"
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
.page-container {
  width: 297mm;
  height: 210mm;
  background-color: var(--page-bg, var(--bg));
}

// Editor mode: scaled down with borders
.album-container:not(.print-mode) {
  contain: strict;

  .page-container {
    scale: 0.8;
    padding: 5mm;
    border: 1px dashed white;
  }
}

// Print mode: exact page sizing, no editor chrome
.album-container.print-mode {
  .page-container {
    overflow: hidden;
    break-after: page;
    break-inside: avoid;
    box-sizing: border-box;
  }
}

@media print {
  .album-container {
    padding: 0;
  }

  .page-container {
    break-after: always;
    break-inside: avoid;
    margin: 0;
  }
}
</style>
