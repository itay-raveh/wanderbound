import { client } from "@/client/client.gen";

/** Build a full URL for a media asset path (e.g. "trip/foo/photos/bar.jpg").
 *  Absolute URLs (http/https) are returned as-is. */
export function mediaUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${client.getConfig().baseUrl}/api/v1/${path}`;
}
