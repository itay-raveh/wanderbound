import { useMutation, useQueryCache } from "@pinia/colada";
import { updateAlbum } from "@/client";
import type { AlbumMeta, AlbumUpdate } from "@/client";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export function useAlbumMutation(aid: () => string) {
  const cache = useQueryCache();
  const undoStack = useUndoStack();

  return useMutation({
    mutation: async (update: AlbumUpdate) => {
      const { data } = await updateAlbum({
        path: { aid: aid() },
        body: update,
      });
      return data;
    },
    onMutate: (update) => {
      const key = queryKeys.album(aid());
      const prev = cache.getQueryData<AlbumMeta>(key);
      if (prev) {
        cache.setQueryData(key, { ...prev, ...update });
        undoStack.push({
          type: "album",
          before: pickSnapshot(
            prev,
            Object.keys(update) as (keyof AlbumUpdate)[],
          ),
          after: { ...update },
        });
      }
      return prev;
    },
    onError: (_error, _vars, prev) => {
      if (prev) {
        cache.setQueryData(queryKeys.album(aid()), prev);
      }
      Notify.create({ type: "negative", message: t("error.saveAlbum") });
    },
  });
}
