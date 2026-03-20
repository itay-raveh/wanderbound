import type { Segment, BoundaryAdjust } from "@/client";
import type { HikeEndpoint } from "@/components/album/map/mapSegments";
import { addLine, lineFeature, removeMapLayer } from "@/components/album/map/mapSegments";
import distance from "@turf/distance";
import nearestPointOnLine from "@turf/nearest-point-on-line";
import mapboxgl from "mapbox-gl";

const HANDLE_CLASS = "hike-handle";

interface DragContext {
  map: mapboxgl.Map;
  hikeSegment: Segment;
  allSegments: Segment[];
  hikeColor: string;
  onCommit: (adjust: BoundaryAdjust) => void;
}

/** Mirror of the adjacency query in albums.py adjust_segment_boundary — keep in sync. */
function findAdjacentSegment(
  segments: Segment[],
  hike: Segment,
  handle: "start" | "end",
): Segment | null {
  let best: Segment | null = null;
  for (const seg of segments) {
    if ((seg.start_time === hike.start_time && seg.end_time === hike.end_time) || seg.kind === "flight") continue;
    if (handle === "start") {
      if (seg.end_time <= hike.start_time && (!best || seg.end_time > best.end_time))
        best = seg;
    } else {
      if (seg.start_time >= hike.end_time && (!best || seg.start_time < best.start_time))
        best = seg;
    }
  }
  return best;
}

/**
 * Sets up draggable boundary handles on hike endpoints.
 * Returns a cleanup function that removes all markers and layers.
 */
export function setupBoundaryHandles(
  endpoints: HikeEndpoint[],
  ctx: DragContext,
): () => void {
  const markers: mapboxgl.Marker[] = [];
  const cleanups: (() => void)[] = [];

  for (const ep of endpoints) {
    const adjacent = findAdjacentSegment(ctx.allSegments, ctx.hikeSegment, ep.handle);

    const el = document.createElement("div");
    el.className = HANDLE_CLASS;
    if (!adjacent) el.classList.add("static");

    const marker = new mapboxgl.Marker({ element: el, draggable: adjacent !== null })
      .setLngLat(ep.coord)
      .addTo(ctx.map);
    markers.push(marker);

    if (!adjacent) continue;

    const isStart = ep.handle === "start";
    const ghostId = `boundary-ghost-${ep.handle}`;

    // Adjacent segments are temporally non-overlapping — concat in time order
    const combinedPoints = isStart
      ? [...adjacent.points, ...ctx.hikeSegment.points]
      : [...ctx.hikeSegment.points, ...adjacent.points];
    const extendedCoords: [number, number][] = combinedPoints.map((p) => [p.lon, p.lat]);
    const extendedLine = lineFeature(extendedCoords);

    // Precompute cumulative geodesic distances along the extended line (km).
    const cumDist = [0];
    for (let i = 1; i < extendedCoords.length; i++) {
      cumDist.push(cumDist[i - 1]! + distance(extendedCoords[i - 1]!, extendedCoords[i]!));
    }

    const originalLngLat = marker.getLngLat();

    const hikeLen = ctx.hikeSegment.points.length;
    const originalHikeCoords = isStart
      ? extendedCoords.slice(adjacent.points.length)
      : extendedCoords.slice(0, hikeLen);

    let snappedTime: number | null = null;
    let rafId = 0;

    /** Interpolate boundary time using geodesic distance along the line. */
    function computeBoundaryTime(location: number, edgeIdx: number): number {
      const t0 = combinedPoints[edgeIdx]!.time;
      if (edgeIdx + 1 >= combinedPoints.length) return t0;
      const t1 = combinedPoints[edgeIdx + 1]!.time;
      const edgeDist = cumDist[edgeIdx + 1]! - cumDist[edgeIdx]!;
      if (edgeDist < 1e-10) return t0;
      const frac = Math.min(1, (location - cumDist[edgeIdx]!) / edgeDist);
      return t0 + frac * (t1 - t0);
    }

    /** Build the hike line with the interpolated snap point as the new boundary. */
    function computeHikeCoords(
      snapIdx: number,
      snapCoord: [number, number],
    ): [number, number][] | null {
      const coords = isStart
        ? [snapCoord, ...extendedCoords.slice(snapIdx + 1)]
        : [...extendedCoords.slice(0, snapIdx + 1), snapCoord];
      return coords.length >= 2 ? coords : null;
    }

    /** Snap marker to nearest point on the extended line and update state. */
    function applySnap(lngLat: mapboxgl.LngLat): boolean {
      const snapped = nearestPointOnLine(extendedLine, [lngLat.lng, lngLat.lat]);
      const [sLng, sLat] = snapped.geometry.coordinates;
      const snapCoord: [number, number] = [sLng!, sLat!];

      const snapIdx = snapped.properties.index ?? 0;
      const location = snapped.properties.location ?? 0;
      const hikeCoords = computeHikeCoords(snapIdx, snapCoord);
      if (!hikeCoords) return false;
      marker.setLngLat(snapCoord);
      snappedTime = computeBoundaryTime(location, snapIdx);
      ep.updateLine(hikeCoords);
      return true;
    }

    function restoreOriginal() {
      cancelAnimationFrame(rafId);
      marker.setLngLat(originalLngLat);
      el.classList.remove("dragging");
      removeMapLayer(ctx.map, ghostId);
      ep.updateLine(originalHikeCoords);
      snappedTime = null;
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        document.removeEventListener("keydown", onKeyDown);
        restoreOriginal();
      }
    };

    cleanups.push(() => {
      cancelAnimationFrame(rafId);
      document.removeEventListener("keydown", onKeyDown);
      removeMapLayer(ctx.map, ghostId);
    });

    marker.on("dragstart", () => {
      el.classList.add("dragging");
      snappedTime = null;
      document.removeEventListener("keydown", onKeyDown);
      document.addEventListener("keydown", onKeyDown);
      removeMapLayer(ctx.map, ghostId);
      addLine(ctx.map, ghostId, extendedLine, {
        "line-color": ctx.hikeColor,
        "line-width": 3,
        "line-dasharray": [3, 3],
        "line-opacity": 0.5,
      });
    });

    marker.on("drag", () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => applySnap(marker.getLngLat()));
    });

    marker.on("dragend", () => {
      cancelAnimationFrame(rafId);
      document.removeEventListener("keydown", onKeyDown);
      el.classList.remove("dragging");

      // Always snap to the final position to avoid stale snappedTime from prior rAF
      if (!applySnap(marker.getLngLat())) {
        restoreOriginal();
        return;
      }

      removeMapLayer(ctx.map, ghostId);
      if (snappedTime === null) return;
      ctx.onCommit({
        start_time: ctx.hikeSegment.start_time,
        end_time: ctx.hikeSegment.end_time,
        handle: ep.handle,
        new_boundary_time: snappedTime,
      });
    });
  }

  return () => {
    for (const cleanup of cleanups) cleanup();
    for (const marker of markers) marker.remove();
  };
}
