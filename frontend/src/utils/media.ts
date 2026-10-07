import { client } from "@/client/client.gen";
import type { AlbumMedia } from "@/client";
import { rotatedSize } from "@/utils/photoEdit";

export function mediaUrl(name: string, albumId: string): string {
  return `${client.getConfig().baseUrl}/api/v1/albums/${albumId}/media/${name}`;
}

export function placementMediaUrl(
  name: string,
  albumId: string,
  media: AlbumMedia | undefined,
): string {
  const base = mediaUrl(name, albumId);
  if (!media?.panorama) return base;
  const cacheKey = media.updated_at
    ? `?d=${encodeURIComponent(media.updated_at)}`
    : "";
  return `${base}/panorama-render${cacheKey}`;
}

export function isVideo(name: string): boolean {
  return name.endsWith(".mp4");
}

export function isPanorama(media: AlbumMedia | undefined): boolean {
  return media?.panorama_candidate ?? false;
}

export function isCoverEligible(media: AlbumMedia): boolean {
  return !isPortrait(media) && !isPanorama(media) && !isVideo(media.name);
}

export function posterPath(path: string): string {
  return isVideo(path) ? path.replace(".mp4", ".jpg") : path;
}

// Must match backend logic/layout/media.py THUMB_WIDTHS - backend generates thumbnails at these sizes.
export const THUMB_WIDTHS = [200, 800] as const;

export function mediaThumbUrl(
  name: string,
  albumId: string,
  width: number = THUMB_WIDTHS[0],
  cacheKey?: string,
): string {
  const suffix = cacheKey ? `&d=${encodeURIComponent(cacheKey)}` : "";
  return `${mediaUrl(posterPath(name), albumId)}?w=${width}${suffix}`;
}

export function flagUrl(countryCode: string): string {
  return `/flags/${countryCode.toLowerCase()}.png`;
}

/** Portrait: aspect ratio < 9:10 (taller than wide). Must match backend layout/media.py. */
export function isPortrait(media: {
  width: number;
  height: number;
  photo_edit?: { angle: number; width: number; height: number } | null;
}): boolean {
  const edit = media.photo_edit;
  if (!edit) return media.width / media.height < 9 / 10;
  const size = rotatedSize(media.width, media.height, edit.angle);
  return (size.width * edit.width) / (size.height * edit.height) < 9 / 10;
}

/** Name-based portrait check via a media lookup map. */
export function isPortraitByName(
  name: string,
  mediaByName: ReadonlyMap<
    string,
    {
      width: number;
      height: number;
      photo_edit?: { angle: number; width: number; height: number } | null;
    }
  >,
): boolean {
  const m = mediaByName.get(name);
  return m ? isPortrait(m) : false;
}

export function weatherIconUrl(iconName: string): string {
  return `/weather-icons/${iconName}.svg`;
}
