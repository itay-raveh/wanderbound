import { Dark, format } from "quasar";
import {
  generateChaptersPdf,
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

export type PdfExportTarget =
  | { type: "album" }
  | { type: "chapter"; id: string }
  | { type: "chapters"; ids: string[] };

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

async function openPdfStream(
  aid: string,
  current: PdfExportTarget,
  signal: AbortSignal,
): Promise<AsyncIterable<PdfEvent>> {
  const common = {
    path: { aid },
    signal,
    sseMaxRetryAttempts: 0,
  };
  const { stream } =
    current.type === "chapters"
      ? await generateChaptersPdf({
          ...common,
          query: { dark: Dark.isActive, chapters: current.ids },
        })
      : await generatePdf({
          ...common,
          query: {
            dark: Dark.isActive,
            chapter: current.type === "chapter" ? current.id : undefined,
          },
        });
  return stream as AsyncIterable<PdfEvent>;
}

function progressMessage(event: PdfProgressEvent, total: number | null): string {
  if (event.phase === "loading") {
    return total != null
      ? t("pdf.loadingProgress", { done: event.done, total })
      : t("common.loadingAlbum");
  }
  if (total != null) {
    return t("pdf.renderingChapters", { done: event.done, total });
  }
  return event.done > 0
    ? t("pdf.renderingBytes", { size: humanStorageSize(event.done) })
    : t("pdf.renderingSingle");
}

function exportFilename(aid: string, current: PdfExportTarget): string {
  if (current.type === "chapters") return `${aid}-chapters.zip`;
  if (current.type === "chapter") return `${aid}-${current.id}.pdf`;
  return `${aid}.pdf`;
}

const idleProgress = (): PdfProgress => ({
  phase: "queued",
  done: 0,
  total: null,
  message: "",
});

export function usePdfExportStream(
  aid: () => string,
  target: () => PdfExportTarget = () => ({ type: "album" }),
): PdfExportHandle {
  const progress = ref<PdfProgress>(idleProgress());

  const handle = usePolledExportDownload<PdfEvent>({
    headless: true,
    async connect(signal) {
      return openPdfStream(aid(), target(), signal);
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
          const msg = progressMessage(event, total);
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
    filename: () => exportFilename(aid(), target()),
    errorMessage: () => t("error.pdfExport"),
    initialMessage: () => t("pdf.queued"),
  });

  // Reset progress when stream returns to idle (after done timer or abort).
  watch(handle.state, (s) => {
    if (s === "idle") {
      progress.value = idleProgress();
    }
  });

  return { ...handle, progress };
}
