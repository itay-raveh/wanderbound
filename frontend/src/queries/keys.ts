export const queryKeys = {
  albums: () => ["albums"] as const,
  album: (aid: string) => [...queryKeys.albums(), aid] as const,
  steps: (aid: string, ranges: string) =>
    [...queryKeys.albums(), aid, "steps", ranges] as const,
  user: () => ["user"] as const,
};
