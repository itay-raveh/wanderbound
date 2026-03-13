/**
 * Mapbox Map Matching API — snaps GPS traces to roads/trails.
 *
 * Long traces are split into overlapping chunks to avoid the API's
 * 100-coordinate limit without aggressive simplification.
 */
import { lineString } from "@turf/helpers";
import simplify from "@turf/simplify";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const MAX_COORDS = 100;

/** Chunk size for splitting long traces. Each chunk stays within the API limit. */
const CHUNK_SIZE = 90;
/** Overlap between consecutive chunks for continuity at boundaries. */
const CHUNK_OVERLAP = 10;

/** Reduce a coordinate array to at most `max` points using Douglas-Peucker. */
function reduceCoords(
  coords: [number, number][],
  max: number,
): [number, number][] {
  if (coords.length <= max) return coords;

  let tolerance = 0.0001;
  let result = coords;
  while (result.length > max) {
    const simplified = simplify(lineString(coords), {
      tolerance,
      highQuality: true,
    });
    result = simplified.geometry.coordinates as [number, number][];
    tolerance *= 2;
  }
  return result;
}

/** Match a single chunk (≤ MAX_COORDS points) against the Map Matching API. */
async function matchChunk(
  coords: [number, number][],
  profile: "driving" | "walking",
): Promise<[number, number][] | null> {
  const reduced = reduceCoords(coords, MAX_COORDS);
  const coordStr = reduced.map(([lng, lat]) => `${lng},${lat}`).join(";");
  const url = `https://api.mapbox.com/matching/v5/mapbox/${profile}/${coordStr}?geometries=geojson&overview=full&tidy=true&access_token=${MAPBOX_TOKEN}`;

  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    const matchings = data.matchings;
    if (!matchings?.length) return null;

    const allCoords: [number, number][] = [];
    for (const matching of matchings) {
      if (matching.geometry?.type === "LineString") {
        const mc = matching.geometry.coordinates as [number, number][];
        allCoords.push(...(allCoords.length > 0 ? mc.slice(1) : mc));
      }
    }
    return allCoords.length >= 2 ? allCoords : null;
  } catch {
    return null;
  }
}

/** Snap coordinates to roads/trails via the Mapbox Map Matching API. Returns null on failure. */
export async function matchRoute(
  coords: [number, number][],
  profile: "driving" | "walking",
): Promise<[number, number][] | null> {
  if (coords.length < 2) return null;

  // Short traces: match directly (no chunking needed)
  if (coords.length <= MAX_COORDS) {
    return matchChunk(coords, profile);
  }

  // Long traces: split into overlapping chunks so each chunk stays within
  // the API limit without aggressive simplification.
  const chunks: [number, number][][] = [];
  for (let start = 0; start < coords.length; start += CHUNK_SIZE - CHUNK_OVERLAP) {
    const end = Math.min(start + CHUNK_SIZE, coords.length);
    chunks.push(coords.slice(start, end));
    if (end === coords.length) break;
  }

  const results = await Promise.all(chunks.map((chunk) => matchChunk(chunk, profile)));

  // Concatenate matched geometries; skip failed chunks
  const allCoords: [number, number][] = [];
  for (const matched of results) {
    if (!matched) continue;
    allCoords.push(...(allCoords.length > 0 ? matched.slice(1) : matched));
  }

  return allCoords.length >= 2 ? allCoords : null;
}
