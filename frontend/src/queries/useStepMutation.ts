import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep } from "@/client";
import type { AlbumData, StepUpdate } from "@/client";
import { useAlbumStore } from "@/stores/useAlbumStore";
import { Notify } from "quasar";
import { queryKeys } from "./keys";

export function useStepMutation() {
  const cache = useQueryCache();
  const albumStore = useAlbumStore();

  return useMutation({
    mutation: async (payload: { sid: number; layout: StepUpdate }) => {
      const { data } = await updateStep({
        path: { aid: albumStore.albumId, sid: payload.sid },
        body: payload.layout,
      });
      return data;
    },
    onMutate: (payload) => {
      const aid = albumStore.albumId;
      const key = queryKeys.albumData(aid);
      const prev = cache.getQueryData<AlbumData>(key);
      if (prev) {
        cache.setQueryData(key, {
          ...prev,
          steps: prev.steps.map((s) =>
            s.idx === payload.sid ? { ...s, ...payload.layout } : s,
          ),
        });
      }
      return { prev, aid };
    },
    onError: (_error, _vars, ctx) => {
      if (ctx?.prev) {
        cache.setQueryData(queryKeys.albumData(ctx.aid), ctx.prev);
      }
      Notify.create({ type: "negative", message: "Failed to save step layout" });
    },
  });
}
