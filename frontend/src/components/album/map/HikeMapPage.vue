<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "@/composables/useMapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { getCountryColor } from "@/utils/colors";
import { KM_TO_MI, M_TO_FT } from "@/utils/units";
import { along, length as turfLength, lineString } from "@turf/turf";
import { onMounted, useTemplateRef, computed, ref } from "vue";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import ElevationProfile from "./ElevationProfile.vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
  hikeSegment: Segment;
  colors: Record<string, string>;
}>();

const container = useTemplateRef("hike-map");
const { distanceUnit, isKm, locale } = useUserQuery();
const { map, init, fitBounds, startResizeObserver } = useMapbox({ container, locale });

const countryColor = computed(() => {
  if (!props.steps.length) return getCountryColor({}, "");
  return getCountryColor(props.colors, props.steps[0]!.location.country_code);
});

/** Elevation samples at regular intervals along the path. */
const elevationSamples = ref<{ lat: number; lon: number; elevation: number; dist: number }[]>([]);

const stats = computed(() => {
  const pts = props.hikeSegment.points;
  if (pts.length < 2) return { distance: "0", duration: "0h", elevGain: 0 };

  const startTime = pts[0]!.time;
  const endTime = pts[pts.length - 1]!.time;
  const hours = (endTime - startTime) / 3600;

  const samples = elevationSamples.value;
  const hasElev = samples.length >= 2;

  // Slope-corrected 3D distance: on steep terrain, trails must switchback,
  // making the actual horizontal distance longer than the GPS chord.
  const MAX_TRAIL_GRADE = 0.20;
  let totalKm = 0;
  let elevGain = 0;

  if (hasElev) {
    for (let i = 1; i < samples.length; i++) {
      const dh = (samples[i]!.dist - samples[i - 1]!.dist) * 1000; // chord (m)
      const de = samples[i]!.elevation - samples[i - 1]!.elevation;
      // Trail can't be shorter than the chord, and can't be steeper than
      // MAX_TRAIL_GRADE — whichever constraint binds gives the longer estimate.
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

  return {
    distance: dist.toFixed(1),
    duration: hours >= 24 ? `${Math.ceil(hours / 24)}d` : `${Math.round(hours)}h`,
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

  const samples: { lat: number; lon: number; elevation: number; dist: number }[] = [];

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

onMounted(() => {
  init();
  startResizeObserver();

  map.value?.on("load", () => {
    const m = map.value!;

    // Enable Mapbox terrain DEM for elevation queries
    m.addSource("mapbox-dem", {
      type: "raster-dem",
      url: "mapbox://mapbox.mapbox-terrain-dem-v1",
      tileSize: 512,
      maxzoom: 14,
    });
    m.setTerrain({ source: "mapbox-dem" });

    const hikeIdx = props.segments.indexOf(props.hikeSegment);
    const otherSegments = props.segments.filter((_, i) => i !== hikeIdx);

    void (async () => {
      // Faint background segments (may include driving/walking → map matched)
      await drawSegmentsAndMarkers(m, {
        segments: otherSegments,
        steps: [],
        style: "faint",
      });

      // Prominent hike + step markers (skip cleanup to keep faint layers)
      const coords = await drawSegmentsAndMarkers(m, {
        segments: [props.hikeSegment],
        steps: props.steps,
        skipCleanup: true,
        hikeColor: countryColor.value,
      });

      // Asymmetric padding: more at bottom for the elevation chart overlay
      const el = container.value;
      const bottomPad = el ? el.clientHeight * 0.27 : 200;
      fitBounds(coords, { top: 80, right: 80, bottom: bottomPad, left: 80 });

      // Query elevations once terrain tiles are loaded
      m.once("idle", () => queryElevations(m));
    })();
  });
});

</script>

<template>
  <div class="page-container hike-page">
    <div ref="hike-map" class="hike-map" />
    <div class="hike-overlay">
      <div class="stat">
        <span class="stat-value">{{ stats.distance }}</span>
        <span class="stat-unit">{{ distanceUnit() }}</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ stats.duration }}</span>
      </div>
      <div v-if="stats.elevGain > 0" class="stat">
        <span class="stat-value">{{ stats.elevGain }}</span>
        <span class="stat-unit">{{ isKm ? 'm+' : 'ft+' }}</span>
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
.hike-page {
  position: relative;
  overflow: hidden;
}

.hike-map {
  position: absolute;
  inset: 0;
}

.hike-overlay {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
  border-radius: 8px;
  padding: 0.6rem 1rem;
  display: flex;
  gap: 1.2rem;
  z-index: 1;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
  color: white;
}

.stat-value {
  font-size: 1.4rem;
  font-weight: 700;
}

.stat-unit {
  font-size: 0.75rem;
  opacity: 0.7;
}

.elevation-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 25%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 0 1.5rem 0.5rem;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    rgba(24, 24, 28, 0.65) 18%,
    rgba(24, 24, 28, 0.92) 32%,
    rgb(24, 24, 28) 48%
  );
}
</style>
