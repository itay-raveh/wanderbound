import type { Segment, SegmentOutline, BoundaryAdjust } from "@/client";
import type { HikeEndpoint } from "@/components/album/map/mapSegments";
import {
  addLine,
  lineFeature,
  removeMapLayer,
} from "@/components/album/map/mapSegments";
import { t } from "@/i18n";
import distance from "@turf/distance";
import nearestPointOnLine from "@turf/nearest-point-on-line";
import mapboxgl from "mapbox-gl";
import { Notify } from "quasar";

const HANDLE_CLASS = "hike-handle";

const MIN_HIKE_LENGTH_KM = 0.1;

/** Concatenate adj + hike arrays in the correct direction. */
function ordered<T>(adj: T[], hike: T[], isStart: boolean): T[] {
  return isStart ? [...adj, ...hike] : [...hike, ...adj];
}

interface SegmentLike {
  start_time: number;
  end_time: number;
  kind: string;
}

interface DragContext {
  map: mapboxgl.Map;
  hikeSegment: Segment;
  /** Full segments fetched for the expanded time range (includes adjacent). */
  fetchedSegments: Segment[];
  allSegments: SegmentOutline[];
  hikeColor: string;
  onCommit: (adjust: BoundaryAdjust) => void;
}

/** Mirror of the adjacency query in albums.py adjust_segment_boundary - keep in sync. */
export function findAdjacentSegment<T extends SegmentLike>(
  segments: T[],
  hike: { start_time: number; end_time: number },
  handle: "start" | "end",
): T | null {
  let best: T | null = null;
  for (const seg of segments) {
    if (
      (seg.start_time === hike.start_time && seg.end_time === hike.end_time) ||
      seg.kind === "flight"
    )
      continue;
    if (handle === "start") {
      if (
        seg.end_time <= hike.start_time &&
        (!best || seg.end_time > best.end_time)
      )
        best = seg;
    } else {
      if (
        seg.start_time >= hike.end_time &&
        (!best || seg.start_time < best.start_time)
      )
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

  // Hike coords/times are constant across endpoints - compute once.
  const hikeCoords: [number, number][] = ctx.hikeSegment.points.map((p) => [
    p.lon,
    p.lat,
  ]);
  const hikeTimes = ctx.hikeSegment.points.map((p) => p.time);

  for (const ep of endpoints) {
    const adjacentOutline = findAdjacentSegment(
      ctx.allSegments,
      ctx.hikeSegment,
      ep.handle,
    );

    const el = document.createElement("div");
    el.className = HANDLE_CLASS;
    el.setAttribute(
      "aria-label",
      t(ep.handle === "start" ? "hike.adjustStart" : "hike.adjustEnd"),
    );
    if (!adjacentOutline) el.classList.add("static");

    const marker = new mapboxgl.Marker({
      element: el,
      draggable: adjacentOutline !== null,
    })
      .setLngLat(ep.coord)
      .addTo(ctx.map);
    markers.push(marker);

    if (!adjacentOutline) continue;

    const adjacentFull = ctx.fetchedSegments.find(
      (s) =>
        s.start_time === adjacentOutline.start_time &&
        s.end_time === adjacentOutline.end_time,
    );

    const isStart = ep.handle === "start";
    const ghostId = `boundary-ghost-${ep.handle}`;

    const adjCoords: [number, number][] = adjacentFull
      ? adjacentFull.points.map((p) => [p.lon, p.lat])
      : [
          [adjacentOutline.start_coord[1], adjacentOutline.start_coord[0]],
          [adjacentOutline.end_coord[1], adjacentOutline.end_coord[0]],
        ];
    const extendedCoords = ordered(adjCoords, hikeCoords, isStart);

    // Visual ghost: use map-matched route for adjacent when available
    const ghostVisualCoords = adjacentFull?.route
      ? ordered(adjacentFull.route, hikeCoords, isStart)
      : extendedCoords;

    const adjTimes = adjacentFull
      ? adjacentFull.points.map((p) => p.time)
      : [adjacentOutline.start_time, adjacentOutline.end_time];
    const combinedTimes = ordered(adjTimes, hikeTimes, isStart);

    const extendedLine = lineFeature(extendedCoords);

    // Precompute cumulative geodesic distances along the extended line (km).
    const cumDist = [0];
    for (let i = 1; i < extendedCoords.length; i++) {
      cumDist.push(
        cumDist[i - 1] + distance(extendedCoords[i - 1], extendedCoords[i]),
      );
    }

    const originalLngLat = marker.getLngLat();

    const adjLen = adjCoords.length;
    const hikeLen = hikeCoords.length;
    const originalHikeCoords = isStart
      ? extendedCoords.slice(adjLen)
      : extendedCoords.slice(0, hikeLen);

    let snappedTime: number | null = null;
    let rafId = 0;

    /** Interpolate boundary time using geodesic distance along the line. */
    function computeBoundaryTime(location: number, edgeIdx: number): number {
      const t0 = combinedTimes[edgeIdx];
      if (edgeIdx + 1 >= combinedTimes.length) return t0;
      const t1 = combinedTimes[edgeIdx + 1];
      const edgeDist = cumDist[edgeIdx + 1] - cumDist[edgeIdx];
      if (edgeDist < 1e-10) return t0;
      const frac = Math.min(1, (location - cumDist[edgeIdx]) / edgeDist);
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

    const totalExtendedKm = cumDist[cumDist.length - 1];

    /** Snap marker to nearest point on the extended line and update state. */
    function applySnap(lngLat: mapboxgl.LngLat): boolean {
      const snapped = nearestPointOnLine(extendedLine, [
        lngLat.lng,
        lngLat.lat,
      ]);
      const [sLng, sLat] = snapped.geometry.coordinates;
      const snapCoord: [number, number] = [sLng, sLat];

      const snapIdx = snapped.properties.index ?? 0;
      const location = snapped.properties.location ?? 0;
      const hikeCoords = computeHikeCoords(snapIdx, snapCoord);
      if (!hikeCoords) return false;

      const newHikeKm = isStart ? totalExtendedKm - location : location;
      if (newHikeKm < MIN_HIKE_LENGTH_KM) return false;

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
      addLine(ctx.map, ghostId, lineFeature(ghostVisualCoords), {
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
        Notify.create({ type: "warning", message: t("error.trimTooShort") });
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
