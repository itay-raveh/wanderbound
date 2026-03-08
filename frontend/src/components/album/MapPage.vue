<script lang="ts" setup>
import { getHikeDistance, type Segment, type Step } from "@/api";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { date } from "quasar";
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

  draw().catch(console.log);
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

async function draw() {
  if (!map) return;

  // Clear old layers (keep tile layers)
  map.eachLayer((layer) => {
    if (layer instanceof L.Marker || layer instanceof L.Polyline) {
      map?.removeLayer(layer);
    }
  });

  const lineWeight = 6 - props.steps.length / 100;
  const iconSize = 60 - props.steps.length / 5;

  for (const segment of props.segments) {
    if (segment.kind === "flight") {
      const pStart = [segment.points[0]!.lat, segment.points[0]!.lon];
      const pEnd = [
        segment.points[segment.points.length - 1]!.lat,
        segment.points[segment.points.length - 1]!.lon,
      ];
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
      L.polyline(
        segment.points.map((p) => [p.lat, p.lon]),
        {
          color: "white",
          weight: lineWeight,
          dashArray: "1, 10",
        },
      ).addTo(map);

      let pos: L.LatLng = L.latLng(
        segment.points[0]!.lat,
        segment.points[0]!.lon,
      );
      let maxMinDist = -1;

      for (const point of segment.points.slice(
        segment.points.length * (2 / 5),
        segment.points.length * (3 / 5),
      )) {
        const p = L.latLng(point.lat, point.lon);
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

      if (props.steps.length <= 10) {
        const end = new Date(
          segment.points[segment.points.length - 1]!.time * 1000,
        );
        const start = new Date(segment.points[0]!.time * 1000);

        const dt_hours = date.getDateDiff(end, start, "hours");

        const dt_days =
          1 +
          date.getDateDiff(
            date.endOfDate(end, "hour"),
            date.startOfDate(start, "hour"),
            "days",
          );

        const time_text =
          dt_hours <= 24 ? `${dt_hours} hours` : `${dt_days} days`;

        const { data: lengthMeters } = await getHikeDistance({
          body: segment.points,
        });

        L.marker(pos, {
          icon: L.divIcon({
            className: "path-icon",
            html: `<div class="column items-center text-center text-white text-weight-bold" style="text-shadow: 0 0 4px black;">
            <i class="q-icon material-icons" style="font-size: ${iconSize}px;">hiking</i>
            <span style="font-size: ${iconSize / 3}px">${Math.ceil(lengthMeters / 1000)} KM</span>
            <span style="font-size: ${iconSize / 4}px">${time_text}</span>
          </div>`,
            iconSize: [iconSize * 2, iconSize * 2],
            iconAnchor: [iconSize, iconSize / 2],
          }),
        }).addTo(map);
      } else {
        L.marker(pos, {
          icon: L.divIcon({
            className: "path-icon",
            html: `<div class="column items-center text-center text-white text-weight-bold" style="text-shadow: 0 0 4px black;">
            <i class="q-icon material-icons" style="font-size: ${iconSize / 2}px;">hiking</i>
          </div>`,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize, iconSize],
          }),
        }).addTo(map);
      }
    } else if (segment.kind === "walking") {
      L.polyline(
        segment.points.map((p) => [p.lat, p.lon]),
        {
          color: "white",
          weight: lineWeight * 0.5,
          dashArray: "2, 8",
        },
      ).addTo(map);
    } else if (segment.kind === "driving") {
      L.polyline(
        segment.points.map((p) => [p.lat, p.lon]),
        {
          color: "white",
          weight: lineWeight * 0.5,
          opacity: 0.5,
        },
      ).addTo(map);
    }
  }

  // Draw step markers on top of the route

  const bounds: LatLon[] = [];
  for (const step of props.steps) {
    const pnt: LatLon = [step.location.lat, step.location.lon];
    bounds.push(pnt);
    L.marker(pnt, {
      icon: L.divIcon({
        className: "step-marker-icon",
        html: `<div class="custom-marker-inner" style="background-image: url(/api/v1/${step.cover})"/>`,
        iconSize: [iconSize, iconSize],
        iconAnchor: [iconSize / 2, iconSize / 2],
      }),
    }).addTo(map);
  }

  // Add segments to bounds
  for (const segment of props.segments)
    if (segment.kind === "hike")
      bounds.push(...segment.points.map((p) => [p.lat, p.lon]));

  //  Fit map to bounds
  map.fitBounds(bounds, {
    padding: [MAP_PADDING, MAP_PADDING],
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
