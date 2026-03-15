import { client } from "@/client/client.gen";

export function mediaUrl(name: string, albumId: string): string {
  return `${client.getConfig().baseUrl}/api/v1/albums/${albumId}/media/${name}`;
}

export function isVideo(name: string): boolean {
  return name.endsWith(".mp4");
}

export function posterPath(path: string): string {
  return isVideo(path) ? path.replace(".mp4", ".jpg") : path;
}

// Must match backend logic/layout/media.py THUMB_WIDTHS — backend generates thumbnails at these sizes.
export const THUMB_WIDTHS = [400, 1200] as const;
export const EDITOR_ZOOM = 0.7;
// Must match --page-width in App.vue. Can't use CSS vars in img `sizes` attribute.
const PAGE_WIDTH = "297mm";
export const SIZES_FULL = `calc(${PAGE_WIDTH} * ${EDITOR_ZOOM})`;
export const SIZES_HALF = `calc(${PAGE_WIDTH} * ${EDITOR_ZOOM} * 0.5)`;

export function mediaThumbUrl(name: string, albumId: string, width: number = THUMB_WIDTHS[0]): string {
  return `${mediaUrl(name, albumId)}?w=${width}`;
}

export function mediaSrcset(name: string, albumId: string): string {
  const base = mediaUrl(name, albumId);
  return THUMB_WIDTHS.map((w) => `${base}?w=${w} ${w}w`).join(", ");
}

/** Build flagcdn URL for a country code (w160 PNG — crisp at small display sizes). */
export function flagUrl(countryCode: string): string {
  return `https://flagcdn.com/w160/${countryCode.toLowerCase()}.png`;
}
