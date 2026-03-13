/** Placeholder ID used when no album is selected yet (query is disabled). */
const NONE = "__none__";

export const queryKeys = {
  albums: () => ["albums"] as const,
  album: (aid: string | null) => [...queryKeys.albums(), aid ?? NONE] as const,
  albumData: (aid: string | null) => [...queryKeys.album(aid), "data"] as const,
  user: () => ["user"] as const,
};
