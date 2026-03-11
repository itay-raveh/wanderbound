<script lang="ts" setup>
import type { Segment, Step } from "@/client";
import { useMapbox } from "@/composables/useMapbox";
import { drawSegmentsAndMarkers } from "@/composables/useMapSegments";
import { useUserQuery } from "@/queries/useUserQuery";
import { distance, point } from "@turf/turf";
import { onMounted, useTemplateRef, computed, ref } from "vue";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import ElevationProfile from "./ElevationProfile.vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
  hikeSegment: Segment;
}>();

const container = useTemplateRef("hike-map");
const { map, init, fitBounds } = useMapbox({ container });
const { distanceUnit, isKm } = useUserQuery();

const hikeAccent = computed(() =>
  getComputedStyle(document.documentElement)
    .getPropertyValue("--hike-accent")
    .trim() || "#FF6B35",
);

const hikeElevations = ref<number[]>([]);

const stats = computed(() => {
  const pts = props.hikeSegment.points;
  if (pts.length < 2) return { distance: "0", duration: "0h", elevGain: 0 };

  const startTime = pts[0]!.time;
  const endTime = pts[pts.length - 1]!.time;
  const hours = (endTime - startTime) / 3600;

  let totalKm = 0;
  let elevGain = 0;
  const elevs = hikeElevations.value;
  const hasElev = elevs.length === pts.length;

  for (let i = 1; i < pts.length; i++) {
    const horiz = distance(
      point([pts[i - 1]!.lon, pts[i - 1]!.lat]),
      point([pts[i]!.lon, pts[i]!.lat]),
      { units: "kilometers" },
    );
    if (hasElev) {
      const dElev = (elevs[i]! - elevs[i - 1]!) / 1000;
      totalKm += Math.sqrt(horiz ** 2 + dElev ** 2);
      if (elevs[i]! > elevs[i - 1]!) elevGain += elevs[i]! - elevs[i - 1]!;
    } else {
      totalKm += horiz;
    }
  }

  const dist = isKm.value ? totalKm : totalKm * 0.621371;
  const elev = isKm.value ? elevGain : elevGain * 3.28084;

  return {
    distance: dist.toFixed(1),
    duration: hours >= 24 ? `${Math.round(hours / 24)}d` : `${Math.round(hours)}h`,
    elevGain: Math.round(elev),
  };
});

const profilePoints = computed(() => {
  const elevs = hikeElevations.value;
  if (elevs.length !== props.hikeSegment.points.length) return [];
  return props.hikeSegment.points.map((p, i) => ({
    lat: p.lat,
    lon: p.lon,
    elevation: elevs[i]!,
  }));
});

function queryElevations(m: mapboxgl.Map) {
  hikeElevations.value = props.hikeSegment.points.map(
    (pt) => m.queryTerrainElevation(new mapboxgl.LngLat(pt.lon, pt.lat)) ?? 0,
  );
}

onMounted(() => {
  init();
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

      // Prominent hike + step markers
      const coords = await drawSegmentsAndMarkers(m, {
        segments: [props.hikeSegment],
        steps: props.steps,
        hikeAccent: hikeAccent.value,
      });

      fitBounds(coords, 80);

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
    <div class="elevation-strip">
      <ElevationProfile :points="profilePoints" :accent="hikeAccent" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.hike-page {
  display: flex;
  flex-direction: column;
  position: relative;
}

.hike-map {
  flex: 1;
  min-height: 0;
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

.elevation-strip {
  height: 25%;
  min-height: 80px;
  background: var(--bg);
  padding: 0.5rem 1rem;
}
</style>
