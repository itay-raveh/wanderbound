<script lang="ts" setup>
import type { SegmentOutline, StepRead as Step } from "@/client";
import { computed } from "vue";

const props = defineProps<{
  steps: Step[];
  segmentOutlines: SegmentOutline[];
}>();

type Point = { x: number; y: number };
type Coord = { lat: number; lon: number };

const VIEW_W = 1000;
const VIEW_H = 707;
const PAD = 72;

const coords = computed<Coord[]>(() => {
  const result: Coord[] = [];
  for (const seg of props.segmentOutlines) {
    result.push(
      { lat: seg.start_coord[0], lon: seg.start_coord[1] },
      { lat: seg.end_coord[0], lon: seg.end_coord[1] },
    );
  }
  for (const step of props.steps) {
    result.push({ lat: step.location.lat, lon: step.location.lon });
  }
  return result;
});

const bounds = computed(() => {
  const all = coords.value;
  if (!all.length) {
    return {
      minLat: 0,
      maxLat: 1,
      minLon: 0,
      maxLon: 1,
    };
  }
  const lats = all.map((c) => c.lat);
  const lons = all.map((c) => c.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  return {
    minLat,
    maxLat: maxLat === minLat ? minLat + 1 : maxLat,
    minLon,
    maxLon: maxLon === minLon ? minLon + 1 : maxLon,
  };
});

function project(coord: Coord): Point {
  const b = bounds.value;
  const x =
    PAD + ((coord.lon - b.minLon) / (b.maxLon - b.minLon)) * (VIEW_W - PAD * 2);
  const y =
    VIEW_H -
    PAD -
    ((coord.lat - b.minLat) / (b.maxLat - b.minLat)) * (VIEW_H - PAD * 2);
  return { x, y };
}

const segmentLines = computed(() =>
  props.segmentOutlines.map((seg) => ({
    kind: seg.kind,
    from: project({ lat: seg.start_coord[0], lon: seg.start_coord[1] }),
    to: project({ lat: seg.end_coord[0], lon: seg.end_coord[1] }),
  })),
);

const stepMarkers = computed(() =>
  props.steps.map((step) => ({
    id: step.id,
    name: step.name,
    point: project({ lat: step.location.lat, lon: step.location.lon }),
  })),
);
</script>

<template>
  <div class="page-container static-map-page relative-position overflow-hidden">
    <svg
      class="static-map"
      :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <rect class="static-map-bg" :width="VIEW_W" :height="VIEW_H" />
      <line
        v-for="line in segmentLines"
        :key="`${line.kind}-${line.from.x}-${line.from.y}-${line.to.x}-${line.to.y}`"
        class="static-map-route"
        :class="`kind-${line.kind}`"
        :x1="line.from.x"
        :y1="line.from.y"
        :x2="line.to.x"
        :y2="line.to.y"
      />
      <circle
        v-for="marker in stepMarkers"
        :key="marker.id"
        class="static-map-marker"
        :cx="marker.point.x"
        :cy="marker.point.y"
        r="8"
      >
        <title>{{ marker.name }}</title>
      </circle>
    </svg>
  </div>
</template>

<style lang="scss" scoped>
.static-map-page {
  background:
    linear-gradient(135deg, rgba(64, 75, 87, 0.12), rgba(64, 75, 87, 0.02)),
    var(--page-bg, var(--bg));
}

.static-map {
  width: 100%;
  height: 100%;
}

.static-map-bg {
  fill: color-mix(in srgb, var(--bg) 94%, var(--text));
}

.static-map-route {
  stroke: color-mix(in srgb, var(--text) 74%, white);
  stroke-width: 5;
  stroke-linecap: round;
  opacity: 0.82;

  &.kind-flight {
    stroke-dasharray: 12 14;
  }

  &.kind-hike,
  &.kind-walking {
    stroke-width: 4;
    stroke-dasharray: 3 9;
  }
}

.static-map-marker {
  fill: var(--q-primary);
  stroke: var(--bg);
  stroke-width: 4;
}
</style>
