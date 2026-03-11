/**
 * Mapbox Map Matching API — snaps GPS traces to roads.
 *
 * Uses turf.simplify (Douglas-Peucker) to reduce coordinate count
 * below the API's 100-point limit while preserving route shape.
 */
import { lineString, simplify } from "@turf/turf";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const MAX_COORDS = 100;

/** Reduce a coordinate array to at most `max` points using Douglas-Peucker. */
function reduceCoords(
  coords: [number, number][],
  max: number,
): [number, number][] {
  if (coords.length <= max) return coords;

  // Iteratively increase tolerance until we're under the limit
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

/** Snap coordinates to roads via the Mapbox Map Matching API. Returns null on failure. */
export async function matchRoute(
  coords: [number, number][],
  profile: "driving" | "walking",
): Promise<[number, number][] | null> {
  if (coords.length < 2) return null;

  const reduced = reduceCoords(coords, MAX_COORDS);
  const coordStr = reduced.map(([lng, lat]) => `${lng},${lat}`).join(";");
  const url = `https://api.mapbox.com/matching/v5/mapbox/${profile}/${coordStr}?geometries=geojson&overview=full&access_token=${MAPBOX_TOKEN}`;

  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    const geometry = data.matchings?.[0]?.geometry;
    if (geometry?.type === "LineString") {
      return geometry.coordinates as [number, number][];
    }
    return null;
  } catch {
    return null;
  }
}
