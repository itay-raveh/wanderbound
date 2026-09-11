import { exportData } from "@/client";
import { zExportDataResponse } from "@/client/zod.gen";
import { client } from "@/client/client.gen";
import { t } from "@/i18n";
import {
  usePolledExportDownload,
  type PolledExportHandle,
} from "./usePolledExportDownload";

function progressMessage(done: number, total: number): string {
  if (done === 0) return t("export.preparing");
  return t("export.progress", { done, total });
}

export function useDataExport(): PolledExportHandle {
  return usePolledExportDownload({
    schema: zExportDataResponse.element,
    async connect(signal) {
      const { stream } = await exportData({
        signal,
        sseMaxRetryAttempts: 0,
      });
      return stream;
    },
    onEvent(event) {
      switch (event.type) {
        case "progress":
          return {
            loading: progressMessage(event.files_done, event.files_total),
          };
        case "done":
          return { done: event.token };
        case "error":
          return { error: event.detail ?? t("error.dataExport") };
        default:
          return { error: t("error.dataExport") };
      }
    },
    downloadUrl: (token) =>
      `${client.getConfig().baseUrl}/api/v1/users/export/download/${encodeURIComponent(token)}`,
    filename: "wanderbound-export.zip",
    errorMessage: t("error.dataExport"),
    initialMessage: t("export.preparing"),
  });
}
