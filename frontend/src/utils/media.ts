import { client } from "@/client/client.gen";

/** Build a full URL for a media asset path (e.g. "trip/foo/photos/bar.jpg").
 *  Absolute URLs (http/https) are returned as-is. */
export function mediaUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${client.getConfig().baseUrl}/api/v1/${path}`;
}

/** Convert a video .mp4 path to its extracted poster .png path. */
export function posterPath(path: string): string {
  return path.endsWith(".mp4") ? path.replace(".mp4", ".png") : path;
}

/** Build flagcdn URL for a country code. */
export function flagUrl(countryCode: string): string {
  return `https://flagcdn.com/${countryCode.toLowerCase()}.svg`;
}
