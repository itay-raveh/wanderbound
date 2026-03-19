<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "./mapSegments";
import { KM_TO_MI, M_TO_FT } from "@/queries/useUserQuery";
import { useUserQuery } from "@/queries/useUserQuery";
import { getCountryColor } from "@/utils/colors";
import along from "@turf/along";
import { lineString } from "@turf/helpers";
import turfLength from "@turf/length";
import { useTemplateRef, computed, ref } from "vue";
import mapboxgl from "mapbox-gl";
import ElevationProfile from "./ElevationProfile.vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
  hikeSegment: Segment;
}>();

const { albumId, colors } = useAlbum();
const container = useTemplateRef("hike-map");
const { distanceUnit, isKm, locale } = useUserQuery();

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
  if (pts.length < 2) return { distance: "0", duration: "0h", elevGain: 0 };

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
    duration:
      hours >= 24 ? `${Math.ceil(hours / 24)}d` : `${Math.round(hours)}h`,
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

const { fitBounds } = useMapbox({
  container,
  locale,
  onReady: (m) => {
    m.resize();
    try {
      // Enable Mapbox terrain DEM for elevation queries
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

    const hikeIdx = props.segments.indexOf(props.hikeSegment);
    const otherSegments = props.segments.filter((_, i) => i !== hikeIdx);

    try {
      // Faint background segments (may include driving/walking → map matched)
      drawSegmentsAndMarkers(m, {
        segments: otherSegments,
        steps: [],
        albumId: albumId.value,
        style: "faint",
      });

      // Prominent hike + step markers (skip cleanup to keep faint layers)
      const coords = drawSegmentsAndMarkers(m, {
        segments: [props.hikeSegment],
        steps: props.steps,
        albumId: albumId.value,
        skipCleanup: true,
        hikeColor: countryColor.value,
      });

      // Pad bottom so the path stays above the elevation overlay
      fitBounds(coords, { top: 80, right: 80, bottom: 220, left: 80 });

      // Query elevations once terrain tiles are loaded
      m.once("idle", () => {
        try {
          queryElevations(m);
        } catch (e) {
          console.warn("[hike-map] elevation query failed:", e);
        }
      });
    } catch (e) {
      console.warn("[hike-map] segment drawing failed:", e);
    }
  },
});
</script>

<template>
  <div ref="hike-map" class="page-container relative-position overflow-hidden">
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
        <span class="stat-unit">{{ isKm ? "m+" : "ft+" }}</span>
      </div>
    </div>

    <div class="elevation-overlay no-pointer-events">
      <ElevationProfile
        :points="elevationSamples"
        :accent="countryColor"
        :total-dist-km="totalDistKm"
        :is-km="isKm"
        bg-color="var(--page-dark-surface)"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>

.hike-overlay {
  position: absolute;
  top: var(--gap-lg);
  right: var(--gap-lg);
  background: var(--page-dark-overlay);
  border-radius: var(--radius-md);
  padding: var(--gap-md) var(--gap-lg);
  display: flex;
  gap: var(--gap-lg);
  z-index: 1;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: var(--gap-sm);
  color: white;
}

.stat-value {
  font-size: var(--type-xl);
  font-weight: 700;
}

.stat-unit {
  font-size: var(--type-xs);
  opacity: 0.7;
}

// Chart overlay pinned to bottom — the SVG includes its own gradient bg
.elevation-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1;
}
</style>
