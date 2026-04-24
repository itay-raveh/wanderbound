<script lang="ts" setup>
import type { SegmentOutline, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { usePrintMode } from "@/composables/usePrintReady";
import {
  setupBoundaryHandles,
  findAdjacentSegment,
} from "@/composables/useHikeBoundaryDrag";
import { useSegmentBoundaryMutation } from "@/queries/useSegmentBoundaryMutation";
import { useSegmentPointsQuery } from "@/queries/useSegmentPointsQuery";
import { safeMarginMm, safeMarginPx } from "@/composables/useSafeMargin";
import { useUserQuery, KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { getCountryColor, ensureSatelliteContrast } from "../colors";
import along from "@turf/along";
import { lineString } from "@turf/helpers";
import turfLength from "@turf/length";
import { useId, useTemplateRef, computed, ref, watch, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import mapboxgl from "mapbox-gl";
import ElevationProfile from "./ElevationProfile.vue";

const { t } = useI18n();
const fadeGradId = `hike-fade-${useId()}`;

const props = defineProps<{
  steps: Step[];
  segments: SegmentOutline[];
  hikeSegment: SegmentOutline;
  /** All album segments (unfiltered) - needed to find adjacent segments for boundary drag. */
  allSegments: SegmentOutline[];
}>();

const { albumId, colors } = useAlbum();
const container = useTemplateRef("hike-map");
const { isKm, locale, distanceUnit, elevationUnit } = useUserQuery();
const printMode = usePrintMode();
const boundaryMutation = useSegmentBoundaryMutation();

// In editor mode, expand the fetch range to include adjacent segments
// so drag handles have full GPS points (not just outline start/end coords).
const adjBefore = computed(
  () =>
    !printMode &&
    findAdjacentSegment(props.allSegments, props.hikeSegment, "start"),
);
const adjAfter = computed(
  () =>
    !printMode &&
    findAdjacentSegment(props.allSegments, props.hikeSegment, "end"),
);
const fromTime = computed(
  () => (adjBefore.value || null)?.start_time ?? props.hikeSegment.start_time,
);
const toTime = computed(
  () => (adjAfter.value || null)?.end_time ?? props.hikeSegment.end_time,
);

const { data: fetchedSegments } = useSegmentPointsQuery(fromTime, toTime);

const fullHikeSegment = computed(() =>
  fetchedSegments.value?.find(
    (s) =>
      s.start_time === props.hikeSegment.start_time &&
      s.end_time === props.hikeSegment.end_time,
  ),
);

let cleanupHandles: (() => void) | null = null;
let pendingIdleHandler: (() => void) | null = null;
let lastAllCoords: [number, number][] = [];
onUnmounted(() => {
  cleanupHandles?.();
  if (pendingIdleHandler && map.value) {
    map.value.off("idle", pendingIdleHandler);
    pendingIdleHandler = null;
  }
});

const countryColor = computed(() => {
  const raw = props.steps.length
    ? getCountryColor(colors.value, props.steps[0].location.country_code)
    : getCountryColor({}, "");
  return ensureSatelliteContrast(raw);
});

/** Elevation samples at regular intervals along the path. */
const elevationSamples = ref<
  { lat: number; lon: number; elevation: number; dist: number }[]
>([]);

const stats = computed(() => {
  const seg = fullHikeSegment.value;
  if (!seg || seg.points.length < 2) return null;

  const pts = seg.points;
  const startTime = pts[0].time;
  const endTime = pts[pts.length - 1].time;
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
      const dh = (samples[i].dist - samples[i - 1].dist) * 1000; // chord (m)
      const de = samples[i].elevation - samples[i - 1].elevation;
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
      ? t("duration.days", { n: Math.ceil(hours / 24) })
      : t("duration.hours", { n: Math.round(hours) });

  return {
    distance: dist.toFixed(1),
    duration,
    elevGain: Math.round(elev),
  };
});

const ariaLabel = computed(() =>
  stats.value
    ? `${t("hike.mapLabel")} - ${stats.value.distance} ${distanceUnit.value}`
    : t("hike.mapLabel"),
);

const totalDistKm = computed(() =>
  elevationSamples.value.length >= 2
    ? elevationSamples.value[elevationSamples.value.length - 1].dist
    : 0,
);

/**
 * Sample elevation at regular intervals along the hike path using turf.along.
 */
function queryElevations(m: mapboxgl.Map) {
  const seg = fullHikeSegment.value;
  if (!seg || seg.points.length < 2) return;

  const pts = seg.points;
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
    const elev = m.queryTerrainElevation(new mapboxgl.LngLat(lon, lat)) ?? 0;
    samples.push({ lat: lat, lon: lon, elevation: elev, dist });
  }

  // Add the final point if not already at the end
  if (numSamples * chunkKm < totalDist) {
    const lastPt = along(line, totalDist, { units: "kilometers" });
    const [lon, lat] = lastPt.geometry.coordinates;
    const elev = m.queryTerrainElevation(new mapboxgl.LngLat(lon, lat)) ?? 0;
    samples.push({ lat: lat, lon: lon, elevation: elev, dist: totalDist });
  }

  elevationSamples.value = samples;
}

function drawMap(m: mapboxgl.Map, { fitBounds: shouldFit = true } = {}) {
  cleanupHandles?.();
  cleanupHandles = null;

  const hikeSeg = fullHikeSegment.value;
  if (!hikeSeg) return;

  // Other fetched segments for faint background drawing
  const otherSegments = (fetchedSegments.value ?? []).filter(
    (s) =>
      s.start_time !== hikeSeg.start_time || s.end_time !== hikeSeg.end_time,
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
      segments: [hikeSeg],
      steps: props.steps,
      albumId: albumId.value,
      skipCleanup: true,
      hikeColor: countryColor.value,
      draggableEndpoints: !printMode,
    });
    lastAllCoords = allCoords;

    // Set up draggable boundary handles in editor mode
    if (!printMode && hikeEndpoints.length > 0) {
      cleanupHandles = setupBoundaryHandles(hikeEndpoints, {
        map: m,
        hikeSegment: hikeSeg,
        fetchedSegments: fetchedSegments.value ?? [],
        allSegments: props.allSegments,
        hikeColor: countryColor.value,
        onCommit: (adjust) => {
          // Tear down handles immediately so stale times can't be reused
          // before the segment-points refetch triggers drawMap() with fresh data.
          cleanupHandles?.();
          cleanupHandles = null;
          boundaryMutation.mutate(adjust);
        },
      });
    }

    if (shouldFit) refitBounds();
  } catch (e) {
    console.warn("[hike-map] segment drawing failed:", e);
  }
}

/** Refit map bounds with current safe margin padding (no segment redraw). */
function refitBounds() {
  if (!lastAllCoords.length) return;
  // Pad bottom so the path stays above the elevation overlay.
  // The chart SVG has a 500:70 aspect ratio; the gradient fade above
  // it adds roughly another half-chart of hazard zone.
  const el = container.value;
  const chartH = el ? el.clientWidth * (70 / 500) : 110;
  const bottomPad = Math.round(chartH * 1.5);
  const sm = safeMarginPx();
  fitBounds(lastAllCoords, {
    top: 80 + sm,
    right: 80 + sm,
    bottom: bottomPad + sm,
    left: 80 + sm,
  });
}

const { map, fitBounds } = useMapbox({
  container,
  locale,
  preserveDrawingBuffer: printMode,
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

    if (fullHikeSegment.value) {
      drawMap(m);
      scheduleElevationQuery(m);
    }
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

// When fetched data arrives or changes, redraw (onReady handles initial draw if data arrives first)
watch(fullHikeSegment, () => {
  if (!map.value || !fullHikeSegment.value || !map.value.isStyleLoaded())
    return;
  elevationSamples.value = [];
  drawMap(map.value);
  scheduleElevationQuery(map.value);
});

// Refit bounds when safe margin changes so the route stays within the safe zone
watch(safeMarginMm, () => {
  if (!map.value || !fullHikeSegment.value || !map.value.isStyleLoaded())
    return;
  refitBounds();
});
</script>

<template>
  <div
    ref="hike-map"
    role="img"
    :aria-label="ariaLabel"
    class="page-container relative-position overflow-hidden"
  >
    <div v-if="stats" class="stats-block">
      <div class="stats-bg" aria-hidden="true" />
      <div class="stat-distance" :style="{ color: countryColor }">
        {{ stats.distance }} {{ distanceUnit }}
      </div>
      <div class="stat-meta">
        <span>{{ stats.duration }}</span>
        <span v-if="stats.elevGain"
          >↑ {{ stats.elevGain }} {{ elevationUnit }}</span
        >
      </div>
    </div>
    <!-- Fade overlay: SVG gradient with stop-opacity instead of CSS alpha
         stops - Skia's PDF backend renders CSS alpha in gradients as pink.
         Uses currentColor so the resolved --bg hex reaches Skia directly. -->
    <svg
      class="elevation-fade"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient :id="fadeGradId" x1="0" x2="0" y1="1" y2="0">
          <stop offset="0%" stop-color="currentColor" stop-opacity="1" />
          <stop offset="50%" stop-color="currentColor" stop-opacity="0.92" />
          <stop offset="65%" stop-color="currentColor" stop-opacity="0.6" />
          <stop offset="80%" stop-color="currentColor" stop-opacity="0.25" />
          <stop offset="90%" stop-color="currentColor" stop-opacity="0.06" />
          <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
        </linearGradient>
      </defs>
      <rect width="1" height="1" :fill="`url(#${fadeGradId})`" />
    </svg>
    <div class="elevation-chart">
      <ElevationProfile
        :points="elevationSamples"
        :accent="countryColor"
        :total-dist-km="totalDistKm"
        :is-km="isKm"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
// SVG gradient overlay pinned to the bottom of the page, extending past
// the page edge to eliminate satellite slivers. Uses SVG stop-opacity
// instead of CSS alpha functions - Skia's PDF backend renders CSS alpha
// in gradients as pink. currentColor inherits --bg via the `color` prop.
.elevation-fade {
  position: absolute;
  bottom: -2mm;
  left: 0;
  width: 100%;
  // Bottom 40% of this element is the opaque zone (chart area);
  // the rest fades to zero so the top edge is imperceptible.
  height: 35%;
  z-index: 1;
  color: var(--bg);
  print-color-adjust: exact;
}

.elevation-chart {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 2;
  padding-inline: var(--safe-margin, 0mm);
  padding-bottom: max(var(--gap-md), var(--safe-margin, 0mm));
}

// Floating stats pill in the top-right corner of the map page.
// Separate from the chart overlay - readable over any satellite imagery.
.stats-block {
  position: absolute;
  z-index: 2;
  /* rtl:ignore */
  top: calc(var(--gap-lg) + var(--safe-margin, 0mm));
  /* rtl:ignore */
  right: calc(var(--gap-lg) + var(--safe-margin, 0mm));
  /* rtl:ignore */
  text-align: right;
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
  padding: var(--gap-sm-md) var(--gap-md-lg);
  border-radius: var(--radius-md);
  isolation: isolate;
}

// Separate opacity layer for PDF-safe semi-transparency.
// CSS opacity is native PDF graphics state; rgb(var(--XX-rgb)/a) is not.
.stats-bg {
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--bg);
  opacity: 0.8;
  border-radius: inherit;
  print-color-adjust: exact;
}

.stat-distance {
  font-family: var(--font-ui);
  font-weight: 800;
  font-size: var(--type-xl);
  font-variant-numeric: tabular-nums;
  letter-spacing: var(--tracking-tight);
  line-height: 1.1;
}

.stat-meta {
  display: flex;
  gap: var(--gap-md);
  font-family: var(--font-ui);
  font-weight: 500;
  font-size: var(--type-sm);
  font-variant-numeric: tabular-nums;
  color: var(--text-bright);
  line-height: 1.2;
}
</style>
