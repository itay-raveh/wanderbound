import { useMutation } from "@pinia/colada";
import { updateVideoFrame } from "@/client";
import { Notify } from "quasar";

export function useVideoFrameMutation() {
  return useMutation({
    mutation: async (payload: { video: string; timestamp: number }) => {
      const { data } = await updateVideoFrame({
        path: { video: payload.video },
        query: { timestamp: payload.timestamp },
      });
      return data;
    },
    onError: () => {
      Notify.create({ type: "negative", message: "Failed to update video frame" });
    },
  });
}
