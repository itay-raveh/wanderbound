import type { Segment, Step } from "@/client";
import { DEFAULT_COUNTRY_COLOR } from "@/utils/colors";
import { mediaThumbUrl, posterPath } from "@/utils/media";
import { matchRoute } from "@/utils/mapMatching";
import "@/styles/map-segments.css";
import mapboxgl from "mapbox-gl";

const LAYER_PREFIX = "seg-";
const MARKER_CLASS = "map-step-marker";
const FLIGHT_ICON_CLASS = "map-flight-icon";

function cleanup(m: mapboxgl.Map) {
  for (const layer of m.getStyle()?.layers ?? []) {
    if (layer.id.startsWith(LAYER_PREFIX)) m.removeLayer(layer.id);
  }
  for (const id of Object.keys(m.getStyle()?.sources ?? {})) {
    if (id.startsWith(LAYER_PREFIX)) m.removeSource(id);
  }
  // Scope marker removal to this map's container (not the entire document)
  m.getContainer()
    .querySelectorAll(`.${MARKER_CLASS}, .${FLIGHT_ICON_CLASS}`)
    .forEach((el) => el.remove());
}

function addLine(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  paint: mapboxgl.LinePaint,
) {
  m.addSource(id, {
    type: "geojson",
    data: {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: coords },
    },
  });
  m.addLayer({
    id,
    type: "line",
    source: id,
    layout: { "line-cap": "round", "line-join": "round" },
    paint,
  });
}

function addCircle(
  m: mapboxgl.Map,
  id: string,
  coord: [number, number],
  paint: mapboxgl.CirclePaint,
) {
  m.addSource(id, {
    type: "geojson",
    data: {
      type: "Feature",
      properties: {},
      geometry: { type: "Point", coordinates: coord },
    },
  });
  m.addLayer({ id, type: "circle", source: id, paint });
}

function buildFlightArc(
  startLon: number,
  startLat: number,
  endLon: number,
  endLat: number,
  steps = 64,
): [number, number][] {
  const midLon = (startLon + endLon) / 2;
  const midLat = (startLat + endLat) / 2;

  // Perpendicular offset for curvature (proportional to distance)
  const dx = endLon - startLon;
  const dy = endLat - startLat;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const offset = dist * 0.2; // 20% of distance = exaggerated curve

  // Offset perpendicular to the line (always curve left/up for consistency)
  const controlLon = midLon + (dy / dist) * offset;
  const controlLat = midLat - (dx / dist) * offset;

  const arc: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    // Quadratic Bézier
    const lon = u * u * startLon + 2 * u * t * controlLon + t * t * endLon;
    const lat = u * u * startLat + 2 * u * t * controlLat + t * t * endLat;
    arc.push([lon, lat]);
  }
  return arc;
}

function drawFlight(m: mapboxgl.Map, id: string, seg: Segment, faint: boolean) {
  const start = seg.points[0]!;
  const end = seg.points[seg.points.length - 1]!;
  const arcCoords = buildFlightArc(start.lon, start.lat, end.lon, end.lat);

  addLine(m, id, arcCoords, {
    "line-color": "rgba(255, 255, 255, 0.85)",
    "line-width": faint ? 0.8 : 1.2,
    "line-dasharray": [2, 3],
    "line-opacity": faint ? 0.2 : 0.7,
  });

  if (!faint) {
    // Slightly past midpoint (55%) so the icon sits on the descending side of the arc
    const midIdx = Math.floor(arcCoords.length * 0.55);
    const midCoord = arcCoords[midIdx]!;
    const nextCoord = arcCoords[Math.min(midIdx + 1, arcCoords.length - 1)]!;
    const angle =
      (Math.atan2(nextCoord[1] - midCoord[1], nextCoord[0] - midCoord[0]) *
        180) /
      Math.PI;

    const el = document.createElement("div");
    el.className = FLIGHT_ICON_CLASS;
    el.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" style="
      color: rgba(255,255,255,0.95);
      transform: rotate(${90 - angle}deg);
      filter: drop-shadow(0 1px 2px rgba(0,0,0,0.6));
    "><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" fill="currentColor"/></svg>`;
    new mapboxgl.Marker({ element: el }).setLngLat(midCoord).addTo(m);
  }
}

function drawHike(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  faint: boolean,
  color?: string,
) {
  const hikeColor = color ?? DEFAULT_COUNTRY_COLOR;

  if (!faint) {
    // Dark stroke behind the colored line for contrast on satellite imagery
    addLine(m, `${id}-stroke`, coords, {
      "line-color": "rgba(0, 0, 0, 0.5)",
      "line-width": 7,
      "line-opacity": 1,
    });
  }

  addLine(m, id, coords, {
    "line-color": faint ? "rgba(255,255,255,0.3)" : hikeColor,
    "line-width": faint ? 1.5 : 4,
    "line-opacity": faint ? 0.3 : 1,
  });

  if (!faint && coords.length >= 2) {
    const endpointPaint: mapboxgl.CirclePaint = {
      "circle-radius": 6,
      "circle-color": hikeColor,
      "circle-stroke-color": "rgba(0,0,0,0.4)",
      "circle-stroke-width": 2,
    };
    addCircle(m, `${id}-start-pt`, coords[0]!, endpointPaint);
    addCircle(m, `${id}-end-pt`, coords[coords.length - 1]!, endpointPaint);
  }
}

function drawDrivingOrWalking(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  kind: "driving" | "walking",
  faint: boolean,
) {
  const isDriving = kind === "driving";
  addLine(m, id, coords, {
    "line-color": isDriving
      ? "rgba(255, 255, 255, 0.9)"
      : "rgba(255, 255, 255, 0.7)",
    "line-width": faint ? 1 : isDriving ? 2.5 : 1.5,
    "line-dasharray": isDriving ? [1, 0] : [1, 3],
    "line-opacity": faint ? 0.3 : isDriving ? 0.8 : 0.6,
  });
}

function shouldMapMatch(steps: Step[], segments: Segment[]): boolean {
  // Many steps → zoomed out overview → raw GPS is fine
  if (steps.length > 8) return false;
  // No driving/walking to match
  const matchable = segments.filter(
    (s) => s.kind === "driving" || s.kind === "walking",
  );
  if (matchable.length === 0) return false;
  // Too many matchable segments → too many API calls
  if (matchable.length > 6) return false;
  return true;
}

interface DrawOptions {
  segments: Segment[];
  steps: Step[];
  albumId: string;
  style?: "normal" | "faint";
  /** Skip cleanup of existing layers/markers (for layered drawing). */
  skipCleanup?: boolean;
  /** Color for hike trail lines. */
  hikeColor?: string;
}

/** Draw segments and step markers. Returns all coords for fitBounds. */
export function drawSegmentsAndMarkers(
  m: mapboxgl.Map,
  options: DrawOptions,
): [number, number][] {
  if (!options.skipCleanup) cleanup(m);

  const { segments, steps, albumId, style = "normal" } = options;
  const faint = style === "faint";
  const allCoords: [number, number][] = [];
  const useMatching = shouldMapMatch(steps, segments);

  const stylePrefix = faint ? "f-" : "";
  for (const [i, seg] of segments.entries()) {
    const id = `${LAYER_PREFIX}${stylePrefix}${i}`;
    const coords: [number, number][] = seg.points.map((p) => [p.lon, p.lat]);

    switch (seg.kind) {
      case "flight":
        drawFlight(m, id, seg, faint);
        break;
      case "hike":
        drawHike(m, id, coords, faint, options.hikeColor);
        allCoords.push(...coords);
        break;
      case "walking":
      case "driving": {
        const kind = seg.kind;
        // Draw raw GPS immediately; replace with matched geometry when ready
        drawDrivingOrWalking(m, id, coords, kind, faint);
        allCoords.push(...coords);

        if (useMatching) {
          void matchRoute(coords, kind).then((matched) => {
            if (!matched) return;
            try {
              const source = m.getSource(id);
              source?.setData({
                type: "Feature",
                properties: {},
                geometry: { type: "LineString", coordinates: matched },
              });
            } catch {
              // Map was destroyed before matching resolved
            }
          });
        }
        break;
      }
    }
  }

  for (const step of steps) {
    const lngLat: [number, number] = [step.location.lon, step.location.lat];
    allCoords.push(lngLat);

    const el = document.createElement("div");
    el.className = MARKER_CLASS;
    if (step.cover) {
      const coverPath = posterPath(step.cover);
      el.style.backgroundImage = `url(${mediaThumbUrl(coverPath, albumId)})`;
    }
    new mapboxgl.Marker({ element: el }).setLngLat(lngLat).addTo(m);
  }

  return allCoords;
}
