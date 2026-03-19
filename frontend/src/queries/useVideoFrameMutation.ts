import { useMutation } from "@pinia/colada";
import { updateVideoFrame } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { Notify } from "quasar";
import { t } from "@/i18n";

export function useVideoFrameMutation() {
  const { albumId } = useAlbum();

  return useMutation({
    mutation: async (payload: { name: string; timestamp: number }) => {
      const { data } = await updateVideoFrame({
        path: { aid: albumId.value, name: payload.name },
        query: { timestamp: payload.timestamp },
      });
      return data;
    },
    onError: () => {
      Notify.create({ type: "negative", message: t("error.videoFrame") });
    },
  });
}
