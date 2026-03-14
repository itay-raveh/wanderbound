import { useMutation } from "@pinia/colada";
import { updateVideoFrame } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { Notify } from "quasar";

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
      Notify.create({ type: "negative", message: "Failed to update video frame" });
    },
  });
}
