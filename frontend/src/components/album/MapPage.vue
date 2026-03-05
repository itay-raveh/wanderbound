<script lang="ts" setup>
import type { LatLon, Segment, Step } from "@/api";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { onMounted, useTemplateRef, watch } from "vue";
import { date } from "quasar";

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

  console.log(props.segments.map((s) => s.kind));

  const lineWeight = 4 - props.steps.length / 100;
  const iconSize = 50 - props.steps.length / 10;

  for (const segment of props.segments) {
    if (segment.kind === "flight") {
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
        weight: lineWeight / 2,
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
          className: "path-icon",
          html: `<i class="q-icon material-icons" style="transform: rotate(${90 - angle}deg);font-size: ${iconSize / 2}px;">flight</i>`,
          iconSize: [iconSize / 2, iconSize / 2],
        }),
        zIndexOffset: -100,
      }).addTo(map);
    } else if (segment.kind === "hike") {
      L.polyline(segment.latlons, {
        color: "white",
        weight: lineWeight,
        dashArray: "10, 10",
      }).addTo(map);

      const dt_hours = date.getDateDiff(
        new Date(segment.end),
        new Date(segment.start),
        "hours",
      );

      const time_text =
        dt_hours <= 24
          ? `${dt_hours} hours`
          : `${Math.ceil(dt_hours / 24)} days`;

      let pos: L.LatLng = L.latLng(segment.latlons[0]!);
      let maxMinDist = -1;

      for (const latlon of segment.latlons.slice(
        segment.latlons.length * (1 / 2),
        segment.latlons.length * (3 / 4),
      )) {
        const p = L.latLng(latlon[0], latlon[1]);
        let minDistToStep = Infinity;

        for (const step of props.steps) {
          const stepP = L.latLng(step.location.lat, step.location.lon);
          const d = p.distanceTo(stepP);
          if (d < minDistToStep) minDistToStep = d;
        }

        if (minDistToStep > maxMinDist) {
          maxMinDist = minDistToStep;
          pos = p;
        }
      }

      L.marker(pos, {
        icon: L.divIcon({
          className: "path-icon",
          html: `<div class="column items-center text-center text-white text-weight-bold" style="text-shadow: 0 0 4px black;">
            <i class="q-icon material-icons" style="font-size: ${iconSize}px;">hiking</i>
            <span style="font-size: ${iconSize / 3}px">${Math.floor(segment.length_km)} KM</span>
            <span style="font-size: ${iconSize / 4}px">${time_text}</span>
          </div>`,
          iconSize: [iconSize * 2, iconSize * 2],
          iconAnchor: [iconSize, iconSize / 2],
        }),
        zIndexOffset: -100,
      }).addTo(map);
    } else if (segment.kind === "other") {
      L.polyline(segment.latlons, {
        color: "white",
        weight: lineWeight,
      }).addTo(map);
    }
  }

  // Draw step markers on top of the route

  const allBounds: LatLon[] = [];
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

  const displaySegments = [...props.segments];
  if (displaySegments.length >= 2) {
    if (
      displaySegments[0]!.kind === "other" &&
      displaySegments[1]!.kind === "hike"
    )
      displaySegments.shift();
    if (
      displaySegments[displaySegments.length - 1]!.kind === "other" &&
      displaySegments[displaySegments.length - 2]!.kind === "hike"
    )
      displaySegments.pop();
  }

  // Add segments to bounds
  for (const segment of displaySegments) allBounds.push(...segment.latlons);

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

.path-icon {
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5));
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
