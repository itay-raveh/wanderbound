<script lang="ts" setup>
import type { SegmentOutline, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { usePrintMode } from "@/composables/usePrintReady";
import { setupBoundaryHandles, findAdjacentSegment } from "@/composables/useHikeBoundaryDrag";
import { useSegmentBoundaryMutation } from "@/queries/useSegmentBoundaryMutation";
import { useSegmentPointsQuery } from "@/queries/useSegmentPointsQuery";
import { safeMarginMm, safeMarginPx } from "@/composables/useSafeMargin";
import { useUserQuery, KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { getCountryColor, ensureSatelliteContrast } from "../colors";
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
const adjBefore = computed(() => !printMode && findAdjacentSegment(props.allSegments, props.hikeSegment, "start"));
const adjAfter = computed(() => !printMode && findAdjacentSegment(props.allSegments, props.hikeSegment, "end"));
const fromTime = computed(() => (adjBefore.value || null)?.start_time ?? props.hikeSegment.start_time);
const toTime = computed(() => (adjAfter.value || null)?.end_time ?? props.hikeSegment.end_time);

const { data: fetchedSegments } = useSegmentPointsQuery(fromTime, toTime);

const fullHikeSegment = computed(() =>
  fetchedSegments.value?.find(
    (s) => s.start_time === props.hikeSegment.start_time && s.end_time === props.hikeSegment.end_time,
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
    ? getCountryColor(colors.value, props.steps[0]!.location.country_code)
    : getCountryColor({}, "");
  return ensureSatelliteContrast(raw);
});

/** Elevation samples at regular intervals along the path. */
const elevationSamples = ref<
  { lat: number; lon: number; elevation: number; dist: number }[]
>([]);

const stats = computed(() => {
  const seg = fullHikeSegment.value;
  if (!seg || seg.points.length < 2)
    return { distance: "0", duration: t("hike.hours", { n: 0 }), elevGain: 0 };

  const pts = seg.points;
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

  const hikeSeg = fullHikeSegment.value;
  if (!hikeSeg) return;

  // Other fetched segments for faint background drawing
  const otherSegments = (fetchedSegments.value ?? []).filter(
    (s) => s.start_time !== hikeSeg.start_time || s.end_time !== hikeSeg.end_time,
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
        onCommit: (adjust) => boundaryMutation.mutate(adjust),
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
  if (!map.value || !fullHikeSegment.value || !map.value.isStyleLoaded()) return;
  elevationSamples.value = [];
  drawMap(map.value);
  scheduleElevationQuery(map.value);
});

// Refit bounds when safe margin changes so the route stays within the safe zone
watch(safeMarginMm, () => {
  if (!map.value || !fullHikeSegment.value || !map.value.isStyleLoaded()) return;
  refitBounds();
});
</script>

<template>
  <div ref="hike-map" role="img" :aria-label="`${t('hike.mapLabel')} – ${stats.distance} ${distanceUnit}`" class="page-container relative-position overflow-hidden">
    <div class="stats-block">
      <div class="stat-distance" :style="{ color: countryColor }">
        {{ stats.distance }} {{ distanceUnit }}
      </div>
      <div class="stat-meta">
        {{ stats.duration }}
        <template v-if="stats.elevGain">
          <span class="stat-sep">&middot;</span>
          +{{ stats.elevGain }} {{ elevationUnit }}
        </template>
      </div>
    </div>
    <div class="elevation-overlay">
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
// Chart panel pinned to bottom. Gradient starts well above the chart
// content so all ticks/labels sit in the fully-dark zone, and extends
// past the SVG bottom to eliminate any satellite sliver at the page edge.
.elevation-overlay {
  position: absolute;
  bottom: -0.25rem;
  left: 0;
  right: 0;
  z-index: 1;
  padding-top: 0;
  padding-inline: var(--safe-margin, 0mm);
  padding-bottom: max(var(--gap-md), var(--safe-margin, 0mm));
  /* rtl:ignore */
  background:
    linear-gradient(
      to right,
      color-mix(in srgb, var(--bg) 88%, transparent),
      color-mix(in srgb, var(--bg) 88%, transparent) var(--safe-margin, 0mm),
      color-mix(in srgb, var(--bg) 70%, transparent) calc(var(--safe-margin, 0mm) + 4%),
      transparent calc(var(--safe-margin, 0mm) + 12%)
    ),
    linear-gradient(
      to top,
      color-mix(in srgb, var(--bg) 97%, transparent),
      color-mix(in srgb, var(--bg) 97%, transparent) var(--safe-margin, 0mm),
      color-mix(in srgb, var(--bg) 95%, transparent) calc(var(--safe-margin, 0mm) + 15%),
      color-mix(in srgb, var(--bg) 88%, transparent) calc(var(--safe-margin, 0mm) + 35%),
      color-mix(in srgb, var(--bg) 65%, transparent) calc(var(--safe-margin, 0mm) + 60%),
      transparent
    );
  print-color-adjust: exact;
}

// Floating stats pill in the top-right corner of the map page.
// Separate from the chart overlay — readable over any satellite imagery.
.stats-block {
  position: absolute;
  z-index: 2;
  /* rtl:ignore */
  top: max(var(--gap-md), var(--safe-margin, 0mm));
  /* rtl:ignore */
  right: max(var(--gap-md), var(--safe-margin, 0mm));
  /* rtl:ignore */
  text-align: right;
  /* rtl:ignore */
  padding: var(--gap-sm) var(--gap-md);
  background: color-mix(in srgb, var(--bg) 80%, transparent);
  border-radius: var(--radius-sm);
  print-color-adjust: exact;
}

.stat-distance {
  font-family: var(--font-ui);
  font-weight: 800;
  font-size: var(--type-xl);
  letter-spacing: var(--tracking-tight);
  line-height: 1.1;
}

.stat-meta {
  font-family: var(--font-ui);
  font-weight: 600;
  font-size: var(--type-xs);
  color: var(--text-bright);
  line-height: 1.3;
}

.stat-sep {
  color: var(--text-muted);
}
</style>
