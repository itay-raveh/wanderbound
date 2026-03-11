import { useQuery } from "@pinia/colada";
import { readSteps } from "@/client";
import { queryKeys } from "./keys";
import { toRangeList } from "@/utils/ranges";
import type { Ref } from "vue";

export function useStepsQuery(
  aid: Ref<string | null>,
  stepsRanges: Ref<string | null>,
) {
  return useQuery({
    key: () =>
      queryKeys.steps(aid.value ?? "", stepsRanges.value ?? ""),
    query: async () => {
      if (!aid.value || !stepsRanges.value)
        throw new Error("Missing aid or ranges");
      const { data } = await readSteps({
        path: { aid: aid.value },
        body: toRangeList(stepsRanges.value),
      });
      return data;
    },
    enabled: () => !!aid.value && !!stepsRanges.value,
  });
}
