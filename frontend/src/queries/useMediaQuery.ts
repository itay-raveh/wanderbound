import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readMedia } from "@/client";
import { queryKeys } from "./keys";

export function useMediaQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.media(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readMedia({ path: { aid: aid.value } });
      return markRaw(data);
    },
    enabled: () => !!aid.value,
    staleTime: 5 * 60 * 1000,
  });
}
