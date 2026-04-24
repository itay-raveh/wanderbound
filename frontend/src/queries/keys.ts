/** Placeholder ID used when no album is selected yet (query is disabled). */
const NONE = "__none__";

/** Default staleTime for album data queries (5 minutes). */
export const STALE_TIME = 5 * 60 * 1000;

export const queryKeys = {
  albums: () => ["albums"] as const,
  album: (aid: string | null) => [...queryKeys.albums(), aid ?? NONE] as const,
  media: (aid: string | null) => [...queryKeys.album(aid), "media"] as const,
  steps: (aid: string | null) => [...queryKeys.album(aid), "steps"] as const,
  segments: (aid: string | null) =>
    [...queryKeys.album(aid), "segments"] as const,
  segmentPoints: (aid: string | null, from: number, to: number) =>
    [...queryKeys.album(aid), "segment-points", from, to] as const,
  printBundle: (aid: string | null) =>
    [...queryKeys.album(aid), "print-bundle"] as const,
  user: () => ["user"] as const,
  authState: () => ["auth-state"] as const,
};
