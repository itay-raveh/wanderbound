import { useMutation, useQueryCache } from "@pinia/colada";
import { updateStep } from "@/client";
import type { StepsAndSegments, StepLayout } from "@/client";
import { Notify } from "quasar";
import { queryKeys } from "./keys";

export function useStepMutation(
  aid: () => string,
  stepsRanges: () => string,
) {
  const cache = useQueryCache();

  return useMutation({
    mutation: async (payload: { sid: number; layout: StepLayout }) => {
      const { data } = await updateStep({
        path: { aid: aid(), sid: payload.sid },
        body: payload.layout,
      });
      return data;
    },
    onMutate: (payload) => {
      const key = queryKeys.steps(aid(), stepsRanges());
      const prev = cache.getQueryData<StepsAndSegments>(key);
      if (prev) {
        const updated = {
          ...prev,
          steps: prev.steps.map((s) =>
            s.idx === payload.sid ? { ...s, ...payload.layout } : s,
          ),
        };
        cache.setQueryData(key, updated);
      }
      return prev;
    },
    onError: (_error, _vars, prev) => {
      if (prev) {
        cache.setQueryData(queryKeys.steps(aid(), stepsRanges()), prev);
      }
      Notify.create({ type: "negative", message: "Failed to save step layout" });
    },
  });
}
