import { useMutation, useQueryCache } from "@pinia/colada";
import { updateAlbum } from "@/client";
import type { Album, AlbumSettings } from "@/client";
import { Notify } from "quasar";
import { queryKeys } from "./keys";

export function useAlbumMutation(aid: () => string) {
  const cache = useQueryCache();

  return useMutation({
    mutation: async (settings: AlbumSettings) => {
      const { data } = await updateAlbum({
        path: { aid: aid() },
        body: settings,
      });
      return data;
    },
    onMutate: (settings) => {
      const key = queryKeys.album(aid());
      const prev = cache.getQueryData<Album>(key);
      if (prev) {
        cache.setQueryData(key, { ...prev, ...settings });
      }
      return prev;
    },
    onError: (_error, _vars, prev) => {
      if (prev) {
        cache.setQueryData(queryKeys.album(aid()), prev);
      }
      Notify.create({ type: "negative", message: "Failed to save album settings" });
    },
    onSettled: () => {
      void cache.invalidateQueries({ key: queryKeys.album(aid()), exact: true });
    },
  });
}
