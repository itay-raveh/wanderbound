<script lang="ts" setup>
import type { Segment, Step } from "@/api";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { onMounted, useTemplateRef, watch } from "vue";

const props = defineProps<{
  steps: Step[];
  segments: Segment[];
}>();

const mapContainer = useTemplateRef("map-container");
let map: L.Map | null = null;

onMounted(() => {
  if (!mapContainer.value) return;
  map = L.map(mapContainer.value, {
    zoomSnap: 0,
    zoomDelta: 0.1,
    preferCanvas: true,
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    touchZoom: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false,
    keyboard: false,
  });

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  ).addTo(map);
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
  ).addTo(map);

  setTimeout(() => map?.invalidateSize(), 500);

  draw();
});

watch(() => props.segments, draw);

type LatLon = [number, number];

function getBezierPoint(t: number, p0: LatLon, p1: LatLon, p2: LatLon): LatLon {
  const x = (1 - t) * (1 - t) * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0];
  const y = (1 - t) * (1 - t) * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1];
  return [x, y];
}

function getControlPoint(p0: LatLon, p1: LatLon, offsetScale: number): LatLon {
  const mid: LatLon = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  const nx = -dy;
  const ny = dx;
  const k = offsetScale * 0.2;
  return [mid[0] + nx * k, mid[1] + ny * k];
}

function getAngle(p0: LatLon, p1: LatLon): number {
  const dy = p1[0] - p0[0];
  const dx = p1[1] - p0[1];
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

const MAP_PADDING = 100;

function draw() {
  if (!map) return;

  // Clear old layers (keep tile layers)
  map.eachLayer((layer) => {
    if (layer instanceof L.Marker || layer instanceof L.Polyline) {
      map?.removeLayer(layer);
    }
  });

  const lineWeight = 4 - props.steps.length / 100;
  for (const segment of props.segments) {
    if (segment.kind !== "flight") {
      L.polyline(segment.latlons, {
        color: "white",
        weight: lineWeight * 2,
      }).addTo(map);
    } else {
      console.log(segment);
      const pStart = segment.latlons[0];
      const pEnd = segment.latlons[segment.latlons.length - 1];
      if (!pStart || !pEnd) continue;
      const control = getControlPoint(pStart, pEnd, -1);
      const curvePoints: LatLon[] = [];
      for (let i = 0; i <= 100; i++) {
        curvePoints.push(getBezierPoint(i / 100, pStart, control, pEnd));
      }
      L.polyline(curvePoints, {
        weight: lineWeight,
        color: "white",
        dashArray: "1, 5",
        lineCap: "round",
      }).addTo(map);

      // Airplane icon at the midpoint of the curve
      const midT = 0.55;
      const midPos = getBezierPoint(midT, pStart, control, pEnd);
      const posPlus = getBezierPoint(midT + 0.01, pStart, control, pEnd);
      const angle = getAngle(midPos, posPlus);
      L.marker(L.latLng(midPos[0], midPos[1]), {
        icon: L.divIcon({
          className: "plane-icon-container",
          html: `<img src="https://cdn.prod.polarsteps.com/65969828189e33620c7fe02b236c1f2734e312df/assets/airplane-marker.png" style="transform: rotate(${-angle}deg); display: block;" alt="Flight">`,
          iconSize: [16, 15],
        }),
      }).addTo(map);
    }
  }

  // Draw step markers on top of the route

  const allBounds: LatLon[] = [];
  const iconSize = 50 - props.steps.length / 10;
  for (const step of props.steps) {
    const pnt: LatLon = [step.location.lat, step.location.lon];
    allBounds.push(pnt);
    L.marker(pnt, {
      icon: L.divIcon({
        className: "step-marker-icon",
        html: `<div class="custom-marker-inner" style="background-image: url(/api/v1/${step.cover})"/>`,
        iconSize: [iconSize, iconSize],
        iconAnchor: [iconSize / 2, iconSize / 2],
      }),
    }).addTo(map);
  }

  // Fit map to bounds
  map.fitBounds(allBounds, {
    padding: [MAP_PADDING, MAP_PADDING],
    maxZoom: 18,
  });
}
</script>

<template>
  <div ref="map-container" class="page-container" />
</template>

<style lang="scss">
.leaflet-popup-content-wrapper {
  border-radius: 8px;
  padding: 0;
  overflow: hidden;
}

.leaflet-popup-content {
  margin: 0;
  width: 200px !important;
}

.map-popup {
  text-align: center;
  color: #333;
}

.map-popup img {
  width: 100%;
  height: 150px;
  object-fit: cover;
  display: block;
}

.map-popup-text {
  padding: 10px;
}

.map-popup h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.custom-marker-inner {
  height: 100%;
  width: 100%;
  border-radius: 50%;
  border: 3px solid white;
  background-size: cover;
  background-position: center;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.5);
}
</style>
