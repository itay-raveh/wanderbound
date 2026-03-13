export const queryKeys = {
  albums: () => ["albums"] as const,
  album: (aid: string) => [...queryKeys.albums(), aid] as const,
  albumData: (aid: string) => [...queryKeys.album(aid), "data"] as const,
  user: () => ["user"] as const,
};
