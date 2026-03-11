import { useQuery } from "@pinia/colada";
import { readAlbum } from "@/client";
import { queryKeys } from "./keys";
import type { Ref } from "vue";

export function useAlbumQuery(aid: Ref<string | null>) {
  return useQuery({
    key: () => (aid.value ? queryKeys.album(aid.value) : ["albums", "__none__"]),
    query: async () => {
      if (!aid.value) throw new Error("No album selected");
      const { data } = await readAlbum({ path: { aid: aid.value } });
      return data;
    },
    enabled: () => !!aid.value,
  });
}
