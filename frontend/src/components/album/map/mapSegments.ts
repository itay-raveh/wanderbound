import type { Segment, Step } from "@/client";
import { DEFAULT_COUNTRY_COLOR } from "../colors";
import { mediaThumbUrl, posterPath } from "@/utils/media";
import "./map-segments.css";
import mapboxgl from "mapbox-gl";

const LAYER_PREFIX = "seg-";
const MARKER_CLASS = "map-step-marker";
const FLIGHT_ICON_CLASS = "map-flight-icon";
const FAINT_OPACITY = 0.75;

function cleanup(m: mapboxgl.Map) {
  for (const layer of m.getStyle()?.layers ?? []) {
    if (layer.id.startsWith(LAYER_PREFIX)) removeMapLayer(m, layer.id);
  }
  // Scope marker removal to this map's container (not the entire document)
  m.getContainer()
    .querySelectorAll(`.${MARKER_CLASS}, .${FLIGHT_ICON_CLASS}`)
    .forEach((el) => el.remove());
}

export function addLine(
  m: mapboxgl.Map,
  id: string,
  data: GeoJSON.GeoJSON,
  paint: mapboxgl.LinePaint,
) {
  m.addSource(id, { type: "geojson", data });
  m.addLayer({
    id,
    type: "line",
    source: id,
    layout: { "line-cap": "round", "line-join": "round" },
    paint,
  });
}

export function lineFeature(coords: [number, number][]): GeoJSON.Feature<GeoJSON.LineString> {
  return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } };
}

function setSourceData(map: mapboxgl.Map, id: string, data: GeoJSON.GeoJSON) {
  map.getSource<mapboxgl.GeoJSONSource>(id)?.setData(data);
}

export function removeMapLayer(map: mapboxgl.Map, id: string) {
  if (!map.getStyle()) return;
  if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(id)) map.removeSource(id);
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

  addLine(m, id, lineFeature(arcCoords), {
    "line-color": "rgba(255, 255, 255, 0.85)",
    "line-width": faint ? 0.8 : 1.2,
    "line-dasharray": [2, 3],
    "line-opacity": faint ? FAINT_OPACITY : 0.7,
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

interface HikeDrawOptions {
  faint: boolean;
  color?: string;
  draggableEndpoints?: boolean;
}

function drawHike(
  m: mapboxgl.Map,
  id: string,
  coords: [number, number][],
  opts: HikeDrawOptions,
) {
  const hikeColor = opts.color ?? DEFAULT_COUNTRY_COLOR;

  if (!opts.faint) {
    // Dark stroke behind the colored line for contrast on satellite imagery
    addLine(m, `${id}-stroke`, lineFeature(coords), {
      "line-color": "rgba(0, 0, 0, 0.5)",
      "line-width": 7,
      "line-opacity": 1,
    });
  }

  addLine(m, id, lineFeature(coords), {
    "line-color": opts.faint ? "rgba(255, 255, 255, 0.75)" : hikeColor,
    "line-width": opts.faint ? 1.5 : 4,
    "line-opacity": opts.faint ? FAINT_OPACITY : 1,
  });

  if (!opts.faint && coords.length >= 2 && !opts.draggableEndpoints) {
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

/** Per-kind rendering config for driving/walking route layers. */
interface RouteStyle {
  sourceId: string;
  shadowId: string;
  width: number;
  shadowWidth: number;
  shadowOpacity: number;
  dasharray?: number[];
}

const ROUTE_STYLES: Record<"driving" | "walking", RouteStyle> = {
  driving: {
    sourceId: `${LAYER_PREFIX}drive`,
    shadowId: `${LAYER_PREFIX}drive-shadow`,
    width: 4, shadowWidth: 12, shadowOpacity: 0.7,
  },
  walking: {
    sourceId: `${LAYER_PREFIX}walk`,
    shadowId: `${LAYER_PREFIX}walk-shadow`,
    width: 3, shadowWidth: 10, shadowOpacity: 0.6,
    dasharray: [2, 3],
  },
};

function multiLine(
  lines: [number, number][][],
): GeoJSON.Feature<GeoJSON.MultiLineString> {
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "MultiLineString", coordinates: lines },
  };
}

function drawRouteLayers(
  m: mapboxgl.Map,
  coordsByKind: Record<"driving" | "walking", [number, number][][]>,
  faint: boolean,
) {
  for (const [kind, style] of Object.entries(ROUTE_STYLES) as [keyof typeof ROUTE_STYLES, RouteStyle][]) {
    const coords = coordsByKind[kind];
    if (!coords.length) continue;
    const data = multiLine(coords);
    if (!faint) {
      addLine(m, style.shadowId, data, {
        "line-color": "#000000",
        "line-width": style.shadowWidth,
        "line-blur": 8,
        "line-opacity": style.shadowOpacity,
      });
    }
    addLine(m, style.sourceId, data, {
      "line-color": "#ffffff",
      "line-width": faint ? 1.5 : style.width,
      "line-opacity": faint ? FAINT_OPACITY : 1,
      ...(style.dasharray ? { "line-dasharray": style.dasharray } : {}),
    });
  }
}

export interface HikeEndpoint {
  coord: [number, number];
  handle: "start" | "end";
  /** Update the rendered hike line to the given coordinate sequence. */
  updateLine: (coords: [number, number][]) => void;
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
  /** Return endpoint coords for drag handles instead of drawing circle layers. */
  draggableEndpoints?: boolean;
}

interface DrawResult {
  allCoords: [number, number][];
  hikeEndpoints: HikeEndpoint[];
}

/** Draw segments and step markers. Returns all coords for fitBounds + hike endpoint info. */
export function drawSegmentsAndMarkers(
  m: mapboxgl.Map,
  options: DrawOptions,
): DrawResult {
  if (!options.skipCleanup) cleanup(m);

  const { segments, steps, albumId, style = "normal" } = options;
  const faint = style === "faint";
  const allCoords: [number, number][] = [];
  const hikeEndpoints: HikeEndpoint[] = [];

  // Collect driving/walking coords for batched rendering (avoids overlap stacking).
  const routeBuckets: Record<"driving" | "walking", [number, number][][]> = {
    driving: [],
    walking: [],
  };

  const stylePrefix = faint ? "f-" : "";
  for (const [i, seg] of segments.entries()) {
    const id = `${LAYER_PREFIX}${stylePrefix}${i}`;
    const coords: [number, number][] = seg.points.map((p) => [p.lon, p.lat]);

    switch (seg.kind) {
      case "flight":
        drawFlight(m, id, seg, faint);
        break;
      case "hike":
        drawHike(m, id, coords, { faint, color: options.hikeColor, draggableEndpoints: options.draggableEndpoints });
        allCoords.push(...coords);
        if (!faint && coords.length >= 2 && options.draggableEndpoints) {
          const feature = lineFeature(coords);
          const updateLine = (c: [number, number][]) => {
            if (c.length < 2) return;
            feature.geometry.coordinates = c;
            setSourceData(m, id, feature);
            setSourceData(m, `${id}-stroke`, feature);
          };
          hikeEndpoints.push(
            { coord: coords[0]!, handle: "start", updateLine },
            { coord: coords[coords.length - 1]!, handle: "end", updateLine },
          );
        }
        break;
      case "walking":
      case "driving": {
        const kind = seg.kind;
        // Use backend-computed route if available, fall back to raw GPS
        const routeCoords: [number, number][] = seg.route ?? coords;
        routeBuckets[kind].push(routeCoords);
        allCoords.push(...coords);
        break;
      }
    }
  }

  // Draw all driving/walking as batched layers (single source per kind).
  drawRouteLayers(m, routeBuckets, faint);

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

  return { allCoords, hikeEndpoints };
}
