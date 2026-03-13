import { useQuery } from "@pinia/colada";
import { readAlbum } from "@/client";
import { queryKeys } from "./keys";
import type { Ref } from "vue";

export function useAlbumQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.album(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readAlbum({ path: { aid: aid.value } });
      return data;
    },
    enabled: () => !!aid.value,
    staleTime: 5 * 60 * 1000,
  });
}
