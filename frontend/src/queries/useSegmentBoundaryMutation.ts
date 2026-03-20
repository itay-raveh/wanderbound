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
    onSuccess: (data) => {
      cache.setQueryData(queryKeys.albumData(albumId.value), data);
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.adjustBoundary") });
    },
  });
}
