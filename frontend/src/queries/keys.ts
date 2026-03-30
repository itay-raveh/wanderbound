/** Placeholder ID used when no album is selected yet (query is disabled). */
const NONE = "__none__";

export const queryKeys = {
  albums: () => ["albums"] as const,
  album: (aid: string | null) => [...queryKeys.albums(), aid ?? NONE] as const,
  media: (aid: string | null) => [...queryKeys.album(aid), "media"] as const,
  steps: (aid: string | null) => [...queryKeys.album(aid), "steps"] as const,
  segments: (aid: string | null) => [...queryKeys.album(aid), "segments"] as const,
  segmentPoints: (aid: string | null, from: number, to: number) =>
    [...queryKeys.album(aid), "segment-points", from, to] as const,
  printBundle: (aid: string | null) => [...queryKeys.album(aid), "print-bundle"] as const,
  user: () => ["user"] as const,
};
