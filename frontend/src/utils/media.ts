import { client } from "@/client/client.gen";

/** Build a full URL for a media asset via the album-scoped media endpoint. */
export function mediaUrl(name: string, albumId: string): string {
  return `${client.getConfig().baseUrl}/api/v1/albums/${albumId}/media/${name}`;
}

/** Check if a media name is a video (.mp4). */
export function isVideo(name: string): boolean {
  return name.endsWith(".mp4");
}

/** Convert a video .mp4 path to its extracted poster .jpg path. */
export function posterPath(path: string): string {
  return isVideo(path) ? path.replace(".mp4", ".jpg") : path;
}

export const THUMB_WIDTHS = [400, 1200] as const;
export const EDITOR_ZOOM = 0.7;
export const SIZES_FULL = `calc(297mm * ${EDITOR_ZOOM})`;
export const SIZES_HALF = `calc(297mm * ${EDITOR_ZOOM} * 0.5)`;

/** Build a single thumbnail URL at the given width (defaults to smallest). */
export function mediaThumbUrl(name: string, albumId: string, width: number = THUMB_WIDTHS[0]): string {
  return `${mediaUrl(name, albumId)}?w=${width}`;
}

/** Build srcset string for pre-generated WebP thumbnails. */
export function mediaSrcset(name: string, albumId: string): string {
  const base = mediaUrl(name, albumId);
  return THUMB_WIDTHS.map((w) => `${base}?w=${w} ${w}w`).join(", ");
}

/** Build flagcdn URL for a country code (w160 PNG — crisp at small display sizes). */
export function flagUrl(countryCode: string): string {
  return `https://flagcdn.com/w160/${countryCode.toLowerCase()}.png`;
}
