import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readSegments } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";

export function useSegmentsQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.segments(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readSegments({ path: { aid: aid.value } });
      return markRaw(data);
    },
    enabled: () => !!aid.value,
    staleTime: STALE_TIME,
  });
}
