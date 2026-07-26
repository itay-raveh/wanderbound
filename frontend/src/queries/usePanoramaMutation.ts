import { useMutation, useQueryCache } from "@pinia/colada";
import { Notify } from "quasar";
import { disablePanorama, updatePanorama } from "@/client";
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

interface DisablePanoramaPayload {
  aid: string;
  name: string;
}

function updateCachedMedia(
  cache: ReturnType<typeof useQueryCache>,
  media: AlbumMedia,
  aid: string,
): void {
  const key = queryKeys.media(aid);
  const current = cache.getQueryData<AlbumMedia[]>(key);
  if (!current) return;
  cache.setQueryData(
    key,
    current.map((item) => (item.name === media.name ? media : item)),
  );
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
      updateCachedMedia(cache, media, payload.aid);
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.panoramaFrame") });
    },
  });
}

export function useDisablePanoramaMutation() {
  const cache = useQueryCache();
  return useMutation({
    mutation: async (payload: DisablePanoramaPayload) => {
      const { data } = await disablePanorama({
        path: { aid: payload.aid, name: payload.name },
      });
      return data;
    },
    onSuccess: (media, payload) => {
      updateCachedMedia(cache, media, payload.aid);
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.panoramaFrame") });
    },
  });
}
