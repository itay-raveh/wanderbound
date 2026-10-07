import { useMutation, useQueryCache } from "@pinia/colada";
import { updateAlbum } from "@/client";
import type { AlbumMeta, AlbumUpdate } from "@/client";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

// Serialize saves per album so rollback and undo never capture another failed save.
const albumQueues = new Map<string, Promise<void>>();
const requestAlbums = new WeakMap<AlbumUpdate, string>();

export function useAlbumMutation(aid: () => string) {
  const cache = useQueryCache();
  const undoStack = useUndoStack();

  return useMutation({
    mutation: async (update: AlbumUpdate) => {
      const { data } = await updateAlbum({
        path: { aid: requestAlbums.get(update) ?? aid() },
        body: update,
      });
      return data;
    },
    onMutate: async (update) => {
      const albumId = aid();
      requestAlbums.set(update, albumId);
      const pushUndo = undoStack.capturePush();
      const rollbackUndo = undoStack.captureRollback();
      const resumeUndo = undoStack.suspend();
      const previous = albumQueues.get(albumId);
      let release = () => {};
      const queue = new Promise<void>((resolve) => {
        release = resolve;
      });
      albumQueues.set(albumId, queue);
      await previous;
      const key = queryKeys.album(albumId);
      const prev = cache.getQueryData<AlbumMeta>(key);
      let entry: ReturnType<typeof undoStack.push>;
      if (prev) {
        cache.setQueryData(key, { ...prev, ...update });
        entry = pushUndo({
          type: "album",
          before: pickSnapshot(
            prev,
            Object.keys(update) as (keyof AlbumUpdate)[],
          ),
          after: { ...update },
        });
      }
      return { prev, albumId, entry, queue, release, resumeUndo, rollbackUndo };
    },
    onError: (_error, _vars, ctx) => {
      undoStack.discard(ctx?.entry);
      ctx?.rollbackUndo?.();
      if (ctx?.prev) cache.setQueryData(queryKeys.album(ctx.albumId), ctx.prev);
      Notify.create({ type: "negative", message: t("error.saveAlbum") });
    },
    onSettled: (_data, _error, update, ctx) => {
      requestAlbums.delete(update);
      if (
        !ctx?.albumId ||
        ctx.queue === undefined ||
        !ctx.release ||
        !ctx.resumeUndo
      )
        return;
      if (albumQueues.get(ctx.albumId) === ctx.queue)
        albumQueues.delete(ctx.albumId);
      ctx.release();
      ctx.resumeUndo();
    },
  });
}
