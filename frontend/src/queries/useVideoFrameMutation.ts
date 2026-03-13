import { useMutation } from "@pinia/colada";
import { updateVideoFrame } from "@/client";
import { useAlbumId } from "@/composables/useAlbumId";
import { Notify } from "quasar";

export function useVideoFrameMutation() {
  const albumId = useAlbumId();

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
