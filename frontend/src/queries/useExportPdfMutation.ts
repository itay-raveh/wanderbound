import { useMutation } from "@pinia/colada";
import { exportPdf } from "@/client";
import { Dark, Notify } from "quasar";

export function useExportPdfMutation(aid: () => string) {
  return useMutation({
    mutation: async () => {
      const { data } = await exportPdf({
        path: { aid: aid() },
        query: { dark: Dark.isActive },
        parseAs: "blob",
      });
      return data as Blob;
    },
    onError: () => {
      Notify.create({ type: "negative", message: "PDF export failed" });
    },
  });
}
