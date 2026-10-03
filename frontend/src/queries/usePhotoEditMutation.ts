import { useMutation, useQueryCache } from "@pinia/colada";
import { Notify } from "quasar";
import { resetPhotoEdit, updatePhotoEdit } from "@/client";
import type { AlbumMedia, PhotoEdit } from "@/client";
import { t } from "@/i18n";
import { queryKeys } from "./keys";

export function usePhotoEditMutation() {
  const cache = useQueryCache();
  return useMutation({
    mutation: async (payload: {
      aid: string;
      name: string;
      edit: PhotoEdit | null;
    }) => {
      const request = { path: { aid: payload.aid, name: payload.name } };
      const { data } = payload.edit
        ? await updatePhotoEdit({ ...request, body: payload.edit })
        : await resetPhotoEdit(request);
      return data;
    },
    onSuccess: (media: AlbumMedia, payload) => {
      const key = queryKeys.media(payload.aid);
      const current = cache.getQueryData<AlbumMedia[]>(key);
      if (!current) return;
      cache.setQueryData(
        key,
        current.map((item) => (item.name === media.name ? media : item)),
      );
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.photoEdit") });
    },
  });
}
