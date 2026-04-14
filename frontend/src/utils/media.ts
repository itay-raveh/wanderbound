import { client } from "@/client/client.gen";
import { PAGE_WIDTH_MM } from "@/utils/pageSize";

export function mediaUrl(name: string, albumId: string): string {
  return `${client.getConfig().baseUrl}/api/v1/albums/${albumId}/media/${name}`;
}

export function isVideo(name: string): boolean {
  return name.endsWith(".mp4");
}

export function posterPath(path: string): string {
  return isVideo(path) ? path.replace(".mp4", ".jpg") : path;
}

// Must match backend logic/layout/media.py THUMB_WIDTHS - backend generates thumbnails at these sizes.
export const THUMB_WIDTHS = [200, 800] as const;
// Can't use CSS vars in img `sizes` attribute.
// Uses zoom=1 so images are always loaded at full resolution regardless of editor zoom.
const PAGE_WIDTH = `${PAGE_WIDTH_MM}mm`;
export const SIZES_FULL = PAGE_WIDTH;
export const SIZES_HALF = `calc(${PAGE_WIDTH} * 0.5)`;

export function mediaThumbUrl(name: string, albumId: string, width: number = THUMB_WIDTHS[0]): string {
  return `${mediaUrl(name, albumId)}?w=${width}`;
}

export function mediaSrcset(name: string, albumId: string): string {
  const base = mediaUrl(name, albumId);
  return THUMB_WIDTHS.map((w) => `${base}?w=${w} ${w}w`).join(", ");
}

/** Build flagcdn URL for a country code (w160 PNG - crisp at small display sizes). */
export function flagUrl(countryCode: string): string {
  return `https://flagcdn.com/w160/${countryCode.toLowerCase()}.png`;
}

/** Portrait: aspect ratio < 9:10 (taller than wide). Must match backend layout/media.py. */
export function isPortrait(media: { width: number; height: number }): boolean {
  return media.width / media.height < 9 / 10;
}

/** Name-based portrait check via a media lookup map. */
export function isPortraitByName(name: string, mediaByName: ReadonlyMap<string, { width: number; height: number }>): boolean {
  const m = mediaByName.get(name);
  return m ? isPortrait(m) : false;
}

/** Build Basmilius weather icon URL for a WMO icon name. */
export function weatherIconUrl(iconName: string): string {
  return `https://basmilius.github.io/meteocons/production/fill/svg/${iconName}.svg`;
}
