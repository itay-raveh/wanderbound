/**
 * GPS trace routing — snaps segments to roads via Mapbox APIs.
 *
 * Automatically selects the right API based on GPS density:
 * - Dense traces (< 2km avg spacing) → Map Matching API (designed for 5s-interval GPS)
 * - Sparse traces (≥ 2km avg spacing) → Directions API (waypoint-to-waypoint routing)
 *
 * Results are cached in memory by segment identity (start_time:end_time)
 * since segments are immutable (pre-computed at user creation).
 */
import { lineString } from "@turf/helpers";
import simplify from "@turf/simplify";
import length from "@turf/length";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

type Coords = [number, number][];
type Profile = "driving" | "walking";

// ── Density classification ───────────────────────────────────────────

/** Average spacing above this threshold triggers Directions API instead of Map Matching. */
const SPARSE_THRESHOLD_KM = 2;

function isSparse(coords: Coords): boolean {
  if (coords.length < 2) return false;
  const totalKm = length(lineString(coords), { units: "kilometers" });
  return totalKm / (coords.length - 1) > SPARSE_THRESHOLD_KM;
}

// ── Cache (deduplicates in-flight requests) ──────────────────────────

/** Caches the Promise itself so concurrent calls for the same key share one flight. */
const routeCache = new Map<string, Promise<Coords | null>>();

// ── Shared helpers ───────────────────────────────────────────────────

function encodeCoords(coords: Coords): string {
  return coords.map(([lng, lat]) => `${lng},${lat}`).join(";");
}

/** Split coords into overlapping chunks, route each in parallel, concatenate. */
async function chunkedRoute(
  coords: Coords,
  chunkSize: number,
  overlap: number,
  routeChunk: (chunk: Coords) => Promise<Coords | null>,
): Promise<Coords | null> {
  const chunks: Coords[] = [];
  for (let start = 0; start < coords.length; start += chunkSize - overlap) {
    const end = Math.min(start + chunkSize, coords.length);
    chunks.push(coords.slice(start, end));
    if (end === coords.length) break;
  }

  const results = await Promise.all(chunks.map(routeChunk));

  const allCoords: Coords = [];
  for (const piece of results) {
    if (!piece) continue;
    allCoords.push(...(allCoords.length > 0 ? piece.slice(1) : piece));
  }
  return allCoords.length >= 2 ? allCoords : null;
}

// ── Map Matching API (dense traces) ─────────────────────────────────

const MATCH_MAX_COORDS = 100;

function reduceCoords(coords: Coords, max: number): Coords {
  if (coords.length <= max) return coords;

  let tolerance = 0.0001;
  let result = coords;
  while (result.length > max) {
    const simplified = simplify(lineString(coords), {
      tolerance,
      highQuality: true,
    });
    result = simplified.geometry.coordinates as Coords;
    tolerance *= 2;
  }
  return result;
}

async function matchChunk(
  coords: Coords,
  profile: Profile,
): Promise<Coords | null> {
  const reduced = reduceCoords(coords, MATCH_MAX_COORDS);
  const url = `https://api.mapbox.com/matching/v5/mapbox/${profile}/${encodeCoords(reduced)}?geometries=geojson&overview=full&tidy=true&access_token=${MAPBOX_TOKEN}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      console.warn(`[routing] matching API error: ${res.status}`);
      return null;
    }
    const data = await res.json();
    const matchings = data.matchings;
    if (!matchings?.length) return null;

    const allCoords: Coords = [];
    for (const matching of matchings) {
      if (matching.geometry?.type === "LineString") {
        const mc = matching.geometry.coordinates as Coords;
        allCoords.push(...(allCoords.length > 0 ? mc.slice(1) : mc));
      }
    }
    return allCoords.length >= 2 ? allCoords : null;
  } catch (e) {
    console.warn(`[routing] matching fetch error:`, e);
    return null;
  }
}

async function matchRoute(coords: Coords, profile: Profile): Promise<Coords | null> {
  if (coords.length <= MATCH_MAX_COORDS) return matchChunk(coords, profile);
  return chunkedRoute(coords, 90, 10, (chunk) => matchChunk(chunk, profile));
}

// ── Directions API (sparse traces) ──────────────────────────────────

async function directionsChunk(
  coords: Coords,
  profile: Profile,
): Promise<Coords | null> {
  const url = `https://api.mapbox.com/directions/v5/mapbox/${profile}/${encodeCoords(coords)}?geometries=geojson&overview=full&access_token=${MAPBOX_TOKEN}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      console.warn(`[routing] directions API error: ${res.status}`);
      return null;
    }
    const data = await res.json();
    const route = data.routes?.[0];
    if (!route?.geometry?.coordinates?.length) return null;
    return route.geometry.coordinates as Coords;
  } catch (e) {
    console.warn(`[routing] directions fetch error:`, e);
    return null;
  }
}

async function directionsRoute(coords: Coords, profile: Profile): Promise<Coords | null> {
  if (coords.length <= 25) return directionsChunk(coords, profile);
  return chunkedRoute(coords, 20, 1, (chunk) => directionsChunk(chunk, profile));
}

// ── Public API ───────────────────────────────────────────────────────

export async function routeSegment(
  segment: { start_time: number; end_time: number },
  coords: Coords,
  profile: Profile,
): Promise<Coords | null> {
  if (coords.length < 2) return null;

  const key = `${segment.start_time}:${segment.end_time}`;
  const inflight = routeCache.get(key);
  if (inflight) {
    console.debug(`[routing] cache hit: ${key}`);
    return inflight;
  }

  const sparse = isSparse(coords);
  console.debug(
    `[routing] ${key}: ${coords.length} pts, ${sparse ? "sparse → directions" : "dense → matching"}, profile=${profile}`,
  );

  const promise = sparse
    ? directionsRoute(coords, profile)
    : matchRoute(coords, profile);

  routeCache.set(key, promise);

  const result = await promise;
  if (result) {
    console.debug(`[routing] ${key}: ${coords.length} → ${result.length} pts`);
  } else {
    routeCache.delete(key);
    console.warn(`[routing] no result for ${key}`);
  }
  return result;
}
