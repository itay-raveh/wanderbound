import { Dark } from "quasar";
import {
  generatePdf,
  type PdfDone,
  type PdfError,
  type PdfProgress,
  type PdfQueued,
} from "@/client";
import { client } from "@/client/client.gen";
import { t } from "@/i18n";
import { useSseDownload, type SseDownloadHandle } from "./useSseDownload";

type PdfEvent = PdfQueued | PdfProgress | PdfDone | PdfError;

type Phase = "loading" | "rendering";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function loadingMessage(phase: Phase, done: number): string {
  switch (phase) {
    case "loading":
      return t("pdf.loading");
    case "rendering":
      return done > 0
        ? t("pdf.renderingBytes", { size: formatBytes(done) })
        : t("pdf.renderingSingle");
  }
}

export function usePdfExportStream(aid: () => string): SseDownloadHandle {
  return useSseDownload<PdfEvent>({
    async connect(signal) {
      const { stream } = await generatePdf({
        path: { aid: aid() },
        query: { dark: Dark.isActive },
        signal,
        sseMaxRetryAttempts: 0,
      });
      return stream as AsyncIterable<PdfEvent>;
    },
    onEvent(event) {
      switch (event.type) {
        case "queued":
          return { loading: t("pdf.queued") };
        case "progress":
          return { loading: loadingMessage(event.phase, event.done) };
        case "done":
          return { done: event.token };
        case "error":
          return { error: t("error.pdfExport") };
        default:
          return { error: t("error.pdfExport") };
      }
    },
    downloadUrl: (token) =>
      `${client.getConfig().baseUrl}/api/v1/albums/pdf/download/${encodeURIComponent(token)}`,
    filename: () => `${aid()}.pdf`,
    errorMessage: () => t("error.pdfExport"),
    initialMessage: () => t("pdf.queued"),
    loadingClass: "pdf-loading-overlay",
  });
}
