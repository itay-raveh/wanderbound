/**
 * Draw GPS segments and step markers on a Mapbox GL map.
 *
 * Used by both MapPage (overview) and HikeMapPage (hike-focused).
 */
import type { Segment, Step } from "@/client";
import { mediaUrl } from "@/utils/media";
import { matchRoute } from "@/utils/mapMatching";
import { greatCircle, point } from "@turf/turf";
import mapboxgl from "mapbox-gl";

const LAYER_PREFIX = "seg-";
const MARKER_CLASS = "map-step-marker";
const FLIGHT_ICON_CLASS = "map-flight-icon";

// Inject marker styles once
if (typeof document !== "undefined" && !document.getElementById("map-segment-styles")) {
  const style = document.createElement("style");
  style.id = "map-segment-styles";
  style.textContent = `
    .${MARKER_CLASS} {
      width: 36px; height: 36px; border-radius: 50%;
      border: 2px solid white; background-size: cover; background-position: center;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5); cursor: default;
    }
    .${FLIGHT_ICON_CLASS} { pointer-events: none; line-height: 1; }
  `;
  document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

function cleanup(m: mapboxgl.Map) {
  for (const layer of m.getStyle()?.layers ?? []) {
    if (layer.id.startsWith(LAYER_PREFIX)) m.removeLayer(layer.id);
  }
  for (const id of Object.keys(m.getStyle()?.sources ?? {})) {
    if (id.startsWith(LAYER_PREFIX)) m.removeSource(id);
  }
  document
    .querySelectorAll(`.${MARKER_CLASS}, .${FLIGHT_ICON_CLASS}`)
    .forEach((el) => el.remove());
}

// ---------------------------------------------------------------------------
// Line helpers
// ---------------------------------------------------------------------------

function addLine(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  paint: mapboxgl.LinePaint,
) {
  m.addSource(id, {
    type: "geojson",
    data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } },
  });
  m.addLayer({
    id,
    type: "line",
    source: id,
    layout: { "line-cap": "round", "line-join": "round" },
    paint,
  });
}

// ---------------------------------------------------------------------------
// Segment drawing
// ---------------------------------------------------------------------------

function drawFlight(m: mapboxgl.Map, id: string, seg: Segment, faint: boolean) {
  const start = seg.points[0]!;
  const end = seg.points[seg.points.length - 1]!;
  const arc = greatCircle(point([start.lon, start.lat]), point([end.lon, end.lat]));

  m.addSource(id, { type: "geojson", data: arc });
  m.addLayer({
    id,
    type: "line",
    source: id,
    layout: { "line-cap": "round" },
    paint: {
      "line-color": "rgba(255, 255, 255, 0.8)",
      "line-width": faint ? 1 : 1.5,
      "line-dasharray": [2, 4],
      "line-opacity": faint ? 0.2 : 0.7,
    },
  });

  if (!faint) addFlightIcon(m, arc);
}

function addFlightIcon(m: mapboxgl.Map, arc: ReturnType<typeof greatCircle>) {
  const geom = arc.geometry;
  const arcCoords = geom.type === "LineString" ? geom.coordinates : (geom.coordinates[0] ?? []);
  const midIdx = Math.floor(arcCoords.length * 0.55);
  const midCoord = arcCoords[midIdx];
  const nextCoord = arcCoords[Math.min(midIdx + 1, arcCoords.length - 1)];
  if (!midCoord || !nextCoord) return;

  const angle = (Math.atan2(nextCoord[1]! - midCoord[1]!, nextCoord[0]! - midCoord[0]!) * 180) / Math.PI;
  const el = document.createElement("div");
  el.className = FLIGHT_ICON_CLASS;
  el.innerHTML = `<span class="material-icons" style="
    font-size: 16px; color: rgba(255,255,255,0.9);
    transform: rotate(${90 - angle}deg);
    filter: drop-shadow(0 1px 2px rgba(0,0,0,0.6));
  ">flight</span>`;
  new mapboxgl.Marker({ element: el }).setLngLat([midCoord[0]!, midCoord[1]!]).addTo(m);
}

function drawHike(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  faint: boolean,
  accent?: string,
) {
  addLine(m, id, coords, {
    "line-color": faint ? "rgba(255,255,255,0.3)" : (accent ?? "#FF6B35"),
    "line-width": faint ? 1.5 : 3,
    "line-opacity": faint ? 0.3 : 1,
  });
}

async function drawMatched(
  m: mapboxgl.Map,
  id: string,
  rawCoords: [number, number][],
  profile: "driving" | "walking",
  faint: boolean,
) {
  const coords = (await matchRoute(rawCoords, profile)) ?? rawCoords;
  const isDriving = profile === "driving";

  addLine(m, id, coords, {
    "line-color": isDriving ? "rgba(255, 255, 255, 0.9)" : "rgba(255, 255, 255, 0.7)",
    "line-width": faint ? 1 : isDriving ? 2.5 : 1.5,
    "line-dasharray": isDriving ? [1, 0] : [1, 3],
    "line-opacity": faint ? 0.3 : isDriving ? 0.8 : 0.6,
  });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

interface DrawOptions {
  segments: Segment[];
  steps: Step[];
  style?: "normal" | "faint";
  hikeAccent?: string;
}

/** Draw segments and step markers. Returns all coords for fitBounds. */
export async function drawSegmentsAndMarkers(
  m: mapboxgl.Map,
  options: DrawOptions,
): Promise<[number, number][]> {
  cleanup(m);

  const { segments, steps, style = "normal", hikeAccent } = options;
  const faint = style === "faint";
  const allCoords: [number, number][] = [];

  for (const [i, seg] of segments.entries()) {
    const id = `${LAYER_PREFIX}${i}`;
    const coords: [number, number][] = seg.points.map((p) => [p.lon, p.lat]);

    switch (seg.kind) {
      case "flight":
        drawFlight(m, id, seg, faint);
        break;
      case "hike":
        drawHike(m, id, coords, faint, hikeAccent);
        allCoords.push(...coords);
        break;
      case "walking":
        await drawMatched(m, id, coords, "walking", faint);
        allCoords.push(...coords);
        break;
      case "driving":
        await drawMatched(m, id, coords, "driving", faint);
        allCoords.push(...coords);
        break;
    }
  }

  for (const step of steps) {
    const lngLat: [number, number] = [step.location.lon, step.location.lat];
    allCoords.push(lngLat);

    const el = document.createElement("div");
    el.className = MARKER_CLASS;
    el.style.backgroundImage = `url(${mediaUrl(step.cover)})`;
    new mapboxgl.Marker({ element: el }).setLngLat(lngLat).addTo(m);
  }

  return allCoords;
}
