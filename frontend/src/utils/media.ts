import { client } from "@/client/client.gen";

/** Build a full URL for a media asset.
 *  Absolute URLs (http/https) are returned as-is (cover photos).
 *  Otherwise resolves via the album-scoped media endpoint. */
export function mediaUrl(name: string, albumId: string): string {
  if (name.startsWith("http://") || name.startsWith("https://")) return name;
  return `${client.getConfig().baseUrl}/api/v1/albums/${albumId}/media/${name}`;
}

/** Check if a media name is a video (.mp4). */
export function isVideo(name: string): boolean {
  return name.endsWith(".mp4");
}

/** Convert a video .mp4 path to its extracted poster .png path. */
export function posterPath(path: string): string {
  return isVideo(path) ? path.replace(".mp4", ".png") : path;
}

/** Build flagcdn URL for a country code. */
export function flagUrl(countryCode: string): string {
  return `https://flagcdn.com/${countryCode.toLowerCase()}.svg`;
}
