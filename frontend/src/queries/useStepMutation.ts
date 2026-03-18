import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep } from "@/client";
import type { AlbumData, StepUpdate } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { Notify } from "quasar";
import { queryKeys } from "./keys";

export function useStepMutation() {
  const cache = useQueryCache();
  const { albumId } = useAlbum();

  return useMutation({
    mutation: async (payload: { sid: number; update: StepUpdate }) => {
      const { data } = await updateStep({
        path: { aid: albumId.value, sid: payload.sid },
        body: payload.update,
      });
      return data;
    },
    onMutate: (payload) => {
      const aid = albumId.value;
      const key = queryKeys.albumData(aid);
      const prev = cache.getQueryData<AlbumData>(key);
      if (prev) {
        cache.setQueryData(key, {
          ...prev,
          steps: prev.steps.map((s) =>
            s.idx === payload.sid ? { ...s, ...payload.update } : s,
          ),
        });
      }
      return { prev, aid };
    },
    onError: (_error, _vars, ctx) => {
      if (ctx?.prev) {
        cache.setQueryData(queryKeys.albumData(ctx.aid), ctx.prev);
      }
      Notify.create({ type: "negative", message: "Failed to save step" });
    },
  });
}
