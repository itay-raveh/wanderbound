import { useQuery } from "@pinia/colada";
import { readAlbumData } from "@/client";
import { queryKeys } from "./keys";
import type { Ref } from "vue";

export function useAlbumDataQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => queryKeys.albumData(aid.value),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readAlbumData({ path: { aid: aid.value } });
      return data;
    },
    enabled: () => !!aid.value,
  });
}
