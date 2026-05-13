import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep, updateStepMediaLayout } from "@/client";
import type { StepMediaLayout, StepRead as Step, StepUpdate } from "@/client";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import type { PhotoFocusSnapshot } from "@/composables/usePhotoFocus";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export type StepMutationUpdate = Partial<StepUpdate & StepMediaLayout>;

interface StepMutationPayload {
  sid: number;
  update: StepMutationUpdate;
  focus?: { before: PhotoFocusSnapshot; after: PhotoFocusSnapshot };
}

function isLayoutUpdate(update: StepMutationUpdate): boolean {
  return "cover" in update || "pages" in update || "unused" in update;
}

function mediaLayout(step: Step, update: StepMutationUpdate): StepMediaLayout {
  return {
    cover: update.cover !== undefined ? update.cover : step.cover,
    pages: update.pages ?? step.pages,
    unused: update.unused ?? step.unused,
  };
}

export function useStepMutation(aid: () => string) {
  const cache = useQueryCache();
  const undoStack = useUndoStack();

  return useMutation({
    mutation: async (payload: StepMutationPayload) => {
      if (isLayoutUpdate(payload.update)) {
        const step = cache
          .getQueryData<Array<Step>>(queryKeys.steps(aid()))
          ?.find((s) => s.id === payload.sid);
        if (!step) throw new Error("Step not found in cache");
        const { data } = await updateStepMediaLayout({
          path: { aid: aid(), sid: payload.sid },
          body: mediaLayout(step, payload.update),
        });
        return data;
      }
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
              Object.keys(payload.update) as (keyof StepMutationUpdate)[],
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
