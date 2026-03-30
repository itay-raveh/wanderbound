import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readAlbum } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";

export function useAlbumQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.album(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readAlbum({ path: { aid: aid.value } });
      return markRaw(data);
    },
    enabled: () => !!aid.value,
    staleTime: STALE_TIME,
  });
}
