import { useQuery } from "@pinia/colada";
import { markRaw, type Ref } from "vue";
import { readSegmentPoints } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";
import { useAlbum } from "@/composables/useAlbum";

export function useSegmentPointsQuery(
  fromTime: Ref<number>,
  toTime: Ref<number>,
) {
  const { albumId } = useAlbum();

  return useQuery({
    key: () =>
      queryKeys.segmentPoints(albumId.value, fromTime.value, toTime.value),
    query: async () => {
      const { data } = await readSegmentPoints({
        path: { aid: albumId.value },
        query: { from_time: fromTime.value, to_time: toTime.value },
      });
      return markRaw(data);
    },
    staleTime: STALE_TIME,
  });
}
