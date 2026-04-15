/** Haversine distance between two WGS84 points, in kilometres. */
export function haversineKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Web Mercator (EPSG:3857) half-circumference in metres: π × 6 378 137 */
const WEB_MERCATOR_EXTENT = 20037508.34;

/** Convert WGS84 lat/lon to SVG-coordinate Web Mercator (y-down). */
export function toSvgMercator(lon: number, lat: number): [number, number] {
  const x = (lon * WEB_MERCATOR_EXTENT) / 180;
  const latRad = (lat * Math.PI) / 180;
  const y =
    -(Math.log(Math.tan(Math.PI / 4 + latRad / 2)) * WEB_MERCATOR_EXTENT) /
    Math.PI;
  return [x, y];
}
