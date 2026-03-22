import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep } from "@/client";
import type { AlbumData, StepUpdate } from "@/client";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export function useStepMutation(aid: () => string) {
  const cache = useQueryCache();
  const undoStack = useUndoStack();

  return useMutation({
    mutation: async (payload: { sid: number; update: StepUpdate }) => {
      const { data } = await updateStep({
        path: { aid: aid(), sid: payload.sid },
        body: payload.update,
      });
      return data;
    },
    onMutate: (payload) => {
      const albumId = aid();
      const key = queryKeys.albumData(albumId);
      const prev = cache.getQueryData<AlbumData>(key);
      if (prev) {
        let oldStep: (typeof prev.steps)[number] | undefined;
        cache.setQueryData(key, {
          ...prev,
          steps: prev.steps.map((s) => {
            if (s.id !== payload.sid) return s;
            oldStep = s;
            return { ...s, ...payload.update };
          }),
        });
        if (oldStep) {
          undoStack.push({
            type: "step",
            sid: payload.sid,
            before: pickSnapshot(oldStep, Object.keys(payload.update) as (keyof StepUpdate)[]),
            after: { ...payload.update },
          });
        }
      }
      return { prev, aid: albumId };
    },
    onError: (_error, _vars, ctx) => {
      if (ctx?.prev) {
        cache.setQueryData(queryKeys.albumData(ctx.aid), ctx.prev);
      }
      Notify.create({ type: "negative", message: t("error.saveStep") });
    },
    onSettled: (_data, _error, _vars, ctx) => {
      if (ctx?.aid) {
        void cache.invalidateQueries({ key: queryKeys.albumData(ctx.aid), exact: true });
      }
    },
  });
}
