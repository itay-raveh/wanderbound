import { useMutation, useQueryCache } from "@pinia/colada";
import { adjustSegmentBoundary } from "@/client";
import type { BoundaryAdjust } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { Notify } from "quasar";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export function useSegmentBoundaryMutation() {
  const cache = useQueryCache();
  const { albumId } = useAlbum();

  return useMutation({
    mutation: async (body: BoundaryAdjust) => {
      const { data } = await adjustSegmentBoundary({
        path: { aid: albumId.value },
        body,
      });
      return data;
    },
    onSuccess: (outlines) => {
      cache.setQueryData(queryKeys.segments(albumId.value), outlines);
      // Segment points are now stale - the boundary changed which points
      // belong to which segment.  Invalidate so HikeMapPage refetches.
      void cache.invalidateQueries({
        key: [...queryKeys.album(albumId.value), "segment-points"],
        exact: false,
      });
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.adjustBoundary") });
    },
  });
}
