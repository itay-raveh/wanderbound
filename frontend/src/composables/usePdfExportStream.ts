import { Dark, format } from "quasar";
import {
  generatePdf,
  type PdfDone,
  type PdfError,
  type PdfProgress as PdfProgressEvent,
  type PdfQueued,
} from "@/client";
import { client } from "@/client/client.gen";
import { t } from "@/i18n";
import {
  usePolledExportDownload,
  type PolledExportHandle,
} from "./usePolledExportDownload";
import { ref, watch, type Ref } from "vue";

type PdfEvent = PdfQueued | PdfProgressEvent | PdfDone | PdfError;

interface PdfProgress {
  phase: "queued" | "loading" | "rendering" | "done";
  done: number;
  total: number | null;
  message: string;
}

interface PdfExportHandle extends PolledExportHandle {
  progress: Ref<PdfProgress>;
}

const { humanStorageSize } = format;

export function usePdfExportStream(aid: () => string): PdfExportHandle {
  const progress = ref<PdfProgress>({
    phase: "queued",
    done: 0,
    total: null,
    message: "",
  });

  const handle = usePolledExportDownload<PdfEvent>({
    headless: true,
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
        case "queued": {
          const msg = t("pdf.queued");
          progress.value = {
            phase: "queued",
            done: 0,
            total: null,
            message: msg,
          };
          return { loading: msg };
        }
        case "progress": {
          const total = event.total ?? null;
          const msg =
            event.phase === "loading"
              ? total != null
                ? t("pdf.loadingProgress", { done: event.done, total })
                : t("common.loadingAlbum")
              : event.done > 0
                ? t("pdf.renderingBytes", {
                    size: humanStorageSize(event.done),
                  })
                : t("pdf.renderingSingle");
          progress.value = {
            phase: event.phase,
            done: event.done,
            total,
            message: msg,
          };
          return { loading: msg };
        }
        case "done":
          progress.value = {
            phase: "done",
            done: 0,
            total: null,
            message: t("pdf.ready"),
          };
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
  });

  // Reset progress when stream returns to idle (after done timer or abort).
  watch(handle.state, (s) => {
    if (s === "idle") {
      progress.value = { phase: "queued", done: 0, total: null, message: "" };
    }
  });

  return { ...handle, progress };
}
