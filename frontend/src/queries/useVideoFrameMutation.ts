import { useMutation } from "@pinia/colada";
import { updateVideoFrame } from "@/client";
import { useAlbumStore } from "@/stores/useAlbumStore";
import { Notify } from "quasar";

export function useVideoFrameMutation() {
  const albumStore = useAlbumStore();

  return useMutation({
    mutation: async (payload: { name: string; timestamp: number }) => {
      const { data } = await updateVideoFrame({
        path: { aid: albumStore.albumId, name: payload.name },
        query: { timestamp: payload.timestamp },
      });
      return data;
    },
    onError: () => {
      Notify.create({ type: "negative", message: "Failed to update video frame" });
    },
  });
}
