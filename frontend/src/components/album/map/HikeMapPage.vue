<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { usePrintMode } from "@/composables/usePrintReady";
import { setupBoundaryHandles } from "@/composables/useHikeBoundaryDrag";
import { useSegmentBoundaryMutation } from "@/queries/useSegmentBoundaryMutation";
import { useUserQuery, KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { getCountryColor } from "../colors";
import along from "@turf/along";
import { lineString } from "@turf/helpers";
import turfLength from "@turf/length";
import { useTemplateRef, computed, ref, watch, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import mapboxgl from "mapbox-gl";
import ElevationProfile from "./ElevationProfile.vue";

const { t } = useI18n();

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
  hikeSegment: Segment;
  /** All album segments (unfiltered) - needed to find adjacent segments for boundary drag. */
  allSegments: Segment[];
}>();

const { albumId, colors } = useAlbum();
const container = useTemplateRef("hike-map");
const { isKm, locale, distanceUnit, elevationUnit } = useUserQuery();
const printMode = usePrintMode();
const boundaryMutation = useSegmentBoundaryMutation();

let cleanupHandles: (() => void) | null = null;
let pendingIdleHandler: (() => void) | null = null;
onUnmounted(() => {
  cleanupHandles?.();
  if (pendingIdleHandler && map.value) {
    map.value.off("idle", pendingIdleHandler);
    pendingIdleHandler = null;
  }
});

const countryColor = computed(() => {
  if (!props.steps.length) return getCountryColor({}, "");
  return getCountryColor(colors.value, props.steps[0]!.location.country_code);
});

/** Elevation samples at regular intervals along the path. */
const elevationSamples = ref<
  { lat: number; lon: number; elevation: number; dist: number }[]
>([]);

const stats = computed(() => {
  const pts = props.hikeSegment.points;
  if (pts.length < 2)
    return { distance: "0", duration: t("hike.hours", { n: 0 }), elevGain: 0 };

  const startTime = pts[0]!.time;
  const endTime = pts[pts.length - 1]!.time;
  const hours = (endTime - startTime) / 3600;

  const samples = elevationSamples.value;
  const hasElev = samples.length >= 2;

  // Slope-corrected 3D distance: on steep terrain, trails must switchback,
  // making the actual horizontal distance longer than the GPS chord.
  const MAX_TRAIL_GRADE = 0.2;
  let totalKm = 0;
  let elevGain = 0;

  if (hasElev) {
    for (let i = 1; i < samples.length; i++) {
      const dh = (samples[i]!.dist - samples[i - 1]!.dist) * 1000; // chord (m)
      const de = samples[i]!.elevation - samples[i - 1]!.elevation;
      // Trail can't be shorter than the chord, and can't be steeper than
      // MAX_TRAIL_GRADE - whichever constraint binds gives the longer estimate.
      const horizontalM = Math.max(dh, Math.abs(de) / MAX_TRAIL_GRADE);
      totalKm += Math.sqrt(horizontalM * horizontalM + de * de) / 1000;

      if (de > 0) elevGain += de;
    }
  } else {
    const coords: [number, number][] = pts.map((p) => [p.lon, p.lat]);
    totalKm = turfLength(lineString(coords), { units: "kilometers" });
  }

  const dist = isKm.value ? totalKm : totalKm * KM_TO_MI;
  const elev = isKm.value ? elevGain : elevGain * M_TO_FT;

  const duration =
    hours >= 24
      ? t("hike.days", { n: Math.ceil(hours / 24) })
      : t("hike.hours", { n: Math.round(hours) });

  return {
    distance: dist.toFixed(1),
    duration,
    elevGain: Math.round(elev),
  };
});

const totalDistKm = computed(() =>
  elevationSamples.value.length >= 2
    ? elevationSamples.value[elevationSamples.value.length - 1]!.dist
    : 0,
);

/**
 * Sample elevation at regular intervals along the hike path using turf.along.
 */
function queryElevations(m: mapboxgl.Map) {
  const pts = props.hikeSegment.points;
  if (pts.length < 2) return;

  const coords: [number, number][] = pts.map((p) => [p.lon, p.lat]);
  const line = lineString(coords);
  const totalDist = turfLength(line, { units: "kilometers" });

  // Target ~500 samples, minimum 20m spacing
  const chunkKm = Math.max(0.02, totalDist / 500);
  const numSamples = Math.floor(totalDist / chunkKm);

  const samples: {
    lat: number;
    lon: number;
    elevation: number;
    dist: number;
  }[] = [];

  for (let i = 0; i <= numSamples; i++) {
    const dist = i * chunkKm;
    const pt = along(line, dist, { units: "kilometers" });
    const [lon, lat] = pt.geometry.coordinates;
    const elev = m.queryTerrainElevation(new mapboxgl.LngLat(lon!, lat!)) ?? 0;
    samples.push({ lat: lat!, lon: lon!, elevation: elev, dist });
  }

  // Add the final point if not already at the end
  if (numSamples * chunkKm < totalDist) {
    const lastPt = along(line, totalDist, { units: "kilometers" });
    const [lon, lat] = lastPt.geometry.coordinates;
    const elev = m.queryTerrainElevation(new mapboxgl.LngLat(lon!, lat!)) ?? 0;
    samples.push({ lat: lat!, lon: lon!, elevation: elev, dist: totalDist });
  }

  elevationSamples.value = samples;
}

function drawMap(m: mapboxgl.Map, { fitBounds: shouldFit = true } = {}) {
  cleanupHandles?.();
  cleanupHandles = null;

  const h = props.hikeSegment;
  const otherSegments = props.segments.filter(
    (s) => s.start_time !== h.start_time || s.end_time !== h.end_time,
  );

  try {
    // Faint background segments (may include driving/walking -> map matched)
    drawSegmentsAndMarkers(m, {
      segments: otherSegments,
      steps: [],
      albumId: albumId.value,
      style: "faint",
    });

    // Prominent hike + step markers (skip cleanup to keep faint layers)
    const { allCoords, hikeEndpoints } = drawSegmentsAndMarkers(m, {
      segments: [props.hikeSegment],
      steps: props.steps,
      albumId: albumId.value,
      skipCleanup: true,
      hikeColor: countryColor.value,
      draggableEndpoints: !printMode,
    });

    // Set up draggable boundary handles in editor mode
    if (!printMode && hikeEndpoints.length > 0) {
      cleanupHandles = setupBoundaryHandles(hikeEndpoints, {
        map: m,
        hikeSegment: props.hikeSegment,
        allSegments: props.allSegments,
        hikeColor: countryColor.value,
        onCommit: (adjust) => boundaryMutation.mutate(adjust),
      });
    }

    if (shouldFit) {
      // Pad bottom so the path stays above the elevation overlay
      fitBounds(allCoords, { top: 80, right: 80, bottom: 250, left: 80 });
    }
  } catch (e) {
    console.warn("[hike-map] segment drawing failed:", e);
  }
}

const { map, fitBounds } = useMapbox({
  container,
  locale,
  onReady: (m) => {
    m.resize();
    try {
      m.addSource("mapbox-dem", {
        type: "raster-dem",
        url: "mapbox://mapbox.mapbox-terrain-dem-v1",
        tileSize: 512,
        maxzoom: 14,
      });
      m.setTerrain({ source: "mapbox-dem" });
    } catch (e) {
      console.warn("[hike-map] terrain setup failed:", e);
    }

    drawMap(m);

    scheduleElevationQuery(m);
  },
});

function scheduleElevationQuery(m: mapboxgl.Map) {
  if (pendingIdleHandler) m.off("idle", pendingIdleHandler);
  const handler = () => {
    m.off("idle", handler);
    pendingIdleHandler = null;
    try {
      queryElevations(m);
    } catch (e) {
      console.warn("[hike-map] elevation query failed:", e);
    }
  };
  pendingIdleHandler = handler;
  m.on("idle", handler);
}

// Re-draw when segment data actually changes (e.g. after boundary mutation).
watch(
  () => [props.hikeSegment.start_time, props.hikeSegment.end_time] as const,
  () => {
    if (!map.value) return;
    elevationSamples.value = [];
    drawMap(map.value);
    scheduleElevationQuery(map.value);
  },
);
</script>

<template>
  <div ref="hike-map" role="img" :aria-label="`${t('hike.mapLabel')} – ${stats.distance} ${distanceUnit}`" class="page-container relative-position overflow-hidden">
    <div class="hike-overlay">
      <span class="text-h6">{{ stats.distance }} {{ distanceUnit }}</span>
      <span class="text-h6">{{ stats.duration }}</span>
      <span v-if="stats.elevGain" class="text-h6"
        >{{ stats.elevGain }} {{ elevationUnit }}+</span
      >
    </div>

    <div class="elevation-overlay">
      <ElevationProfile
        :points="elevationSamples"
        :accent="countryColor"
        :total-dist-km="totalDistKm"
        :is-km="isKm"
        bg-color=""
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.hike-overlay {
  position: absolute;
  top: var(--gap-lg);
  /* rtl:ignore */
  right: var(--gap-lg);
  background: var(--page-dark-overlay);
  border-radius: var(--radius-md);
  padding: var(--gap-md) var(--gap-lg);
  display: flex;
  gap: var(--gap-lg);
  z-index: 1;
}

// Chart overlay pinned to bottom - the SVG includes its own gradient bg
.elevation-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1;
}
</style>
