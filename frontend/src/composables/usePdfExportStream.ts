import { ref, type Ref } from "vue";
import { Dark, Loading, Notify } from "quasar";
import {
  generatePdf,
  type PdfDone,
  type PdfError,
  type PdfProgress,
  type PdfQueued,
} from "@/client";
import { client } from "@/client/client.gen";
import { t } from "@/i18n";

export type PdfStreamState = "idle" | "queued" | "running" | "done" | "error";
type Phase = "loading" | "rendering";

/** hey-api types SSE stream items as Array<union>, but yields individual events. */
type PdfEvent =
  | ({ type: "queued" } & PdfQueued)
  | ({ type: "progress" } & PdfProgress)
  | ({ type: "done" } & PdfDone)
  | ({ type: "error" } & PdfError);

export interface UsePdfExportStream {
  start(): void;
  abort(): void;
  state: Ref<PdfStreamState>;
}


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

export function usePdfExportStream(aid: () => string): UsePdfExportStream {
  const state = ref<PdfStreamState>("idle");
  let controller: AbortController | null = null;
  let lastMsg = "";

  function showLoading(message: string) {
    if (message === lastMsg) return;
    lastMsg = message;
    Loading.show({ message, spinnerColor: "primary", customClass: "pdf-loading-overlay" });
  }

  async function start() {
    controller = new AbortController();
    state.value = "queued";
    showLoading(t("pdf.queued"));

    try {
      const { stream } = await generatePdf({
        path: { aid: aid() },
        query: { dark: Dark.isActive },
        signal: controller.signal,
        sseMaxRetryAttempts: 0,
      });

      let downloadToken: string | null = null;

      for await (const raw of stream) {
        const event = raw as unknown as PdfEvent;
        switch (event.type) {
          case "queued":
            state.value = "queued";
            showLoading(t("pdf.queued"));
            break;
          case "progress":
            state.value = "running";
            showLoading(loadingMessage(event.phase, event.done));
            break;
          case "done":
            downloadToken = event.token;
            break;
          case "error":
            state.value = "error";
            Notify.create({ type: "negative", message: event.detail ?? t("error.pdfExport") });
            return;
        }
      }

      if (downloadToken && !controller.signal.aborted) {
        const a = document.createElement("a");
        a.href = `${client.getConfig().baseUrl}/api/v1/albums/pdf/download/${encodeURIComponent(downloadToken)}`;
        a.download = `${aid()}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        state.value = "done";
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      Notify.create({ type: "negative", message: t("error.pdfExport") });
    } finally {
      Loading.hide();
      lastMsg = "";
      if (state.value === "done") {
        setTimeout(() => {
          state.value = "idle";
        }, 1500);
      }
    }
  }

  function abort() {
    controller?.abort();
    state.value = "idle";
    Loading.hide();
    lastMsg = "";
  }

  return {
    start: () => void start(),
    abort,
    state,
  };
}
