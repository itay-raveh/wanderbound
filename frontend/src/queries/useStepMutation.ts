import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep } from "@/client";
import type { Step, StepUpdate } from "@/client";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import type { PhotoFocusSnapshot } from "@/composables/usePhotoFocus";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

interface StepMutationPayload {
  sid: number;
  update: StepUpdate;
  focus?: { before: PhotoFocusSnapshot; after: PhotoFocusSnapshot };
}

export function useStepMutation(aid: () => string) {
  const cache = useQueryCache();
  const undoStack = useUndoStack();

  return useMutation({
    mutation: async (payload: StepMutationPayload) => {
      const { data } = await updateStep({
        path: { aid: aid(), sid: payload.sid },
        body: payload.update,
      });
      return data;
    },
    onMutate: (payload) => {
      const albumId = aid();
      const key = queryKeys.steps(albumId);
      const prev = cache.getQueryData<Array<Step>>(key);
      if (prev) {
        let oldStep: Step | undefined;
        cache.setQueryData(
          key,
          prev.map((s) => {
            if (s.id !== payload.sid) return s;
            oldStep = s;
            return { ...s, ...payload.update };
          }),
        );
        if (oldStep) {
          undoStack.push({
            type: "step",
            sid: payload.sid,
            before: pickSnapshot(
              oldStep,
              Object.keys(payload.update) as (keyof StepUpdate)[],
            ),
            after: { ...payload.update },
            focus: payload.focus,
          });
        }
      }
      return { prev, aid: albumId };
    },
    onError: (_error, _vars, ctx) => {
      if (ctx?.prev) {
        cache.setQueryData(queryKeys.steps(ctx.aid), ctx.prev);
      }
      Notify.create({ type: "negative", message: t("error.saveStep") });
    },
  });
}
