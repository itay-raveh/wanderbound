import { useMutation, useQueryCache } from "@pinia/colada";
import { Notify } from "quasar";
import { updatePanorama } from "@/client";
import type {
  AlbumMedia,
  PanoramaDestination,
  PanoramaFrameUpdate,
} from "@/client";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export interface PanoramaMutationPayload {
  aid: string;
  name: string;
  frame: PanoramaFrameUpdate;
  destination: PanoramaDestination;
}

export function usePanoramaMutation() {
  const cache = useQueryCache();
  return useMutation({
    mutation: async (payload: PanoramaMutationPayload) => {
      const { data } = await updatePanorama({
        path: { aid: payload.aid, name: payload.name },
        body: {
          frame: payload.frame,
          destination: payload.destination,
        },
      });
      return data;
    },
    onSuccess: (media, payload) => {
      const key = queryKeys.media(payload.aid);
      const current = cache.getQueryData<AlbumMedia[]>(key);
      if (!current) return;
      cache.setQueryData(
        key,
        current.map((item) => (item.name === media.name ? media : item)),
      );
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.panoramaFrame") });
    },
  });
}
