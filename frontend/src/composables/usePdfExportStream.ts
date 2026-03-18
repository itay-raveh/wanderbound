import { ref, type Ref } from "vue";
import { Dark, Loading, Notify } from "quasar";
import {
  generatePdf,
  downloadPdf,
  type PdfDone,
  type PdfError,
  type PdfProgress,
  type PdfQueued,
} from "@/client";

export type PdfStreamState = "idle" | "queued" | "running" | "done" | "error";
type Phase = "loading" | "rendering" | "merging";

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

function loadingMessage(phase: Phase, done: number, total: number): string {
  switch (phase) {
    case "loading":
      return "Loading album\u2026";
    case "rendering":
      return total > 1 ? `Rendering page ${done} / ${total}\u2026` : "Rendering\u2026";
    case "merging":
      return "Merging pages\u2026";
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
    showLoading("Queued\u2026");

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
            showLoading("Queued\u2026");
            break;
          case "progress":
            state.value = "running";
            showLoading(loadingMessage(event.phase, event.done, event.total));
            break;
          case "done":
            downloadToken = event.token;
            break;
          case "error":
            state.value = "error";
            Notify.create({ type: "negative", message: event.detail ?? "PDF export failed" });
            return;
        }
      }

      if (downloadToken && !controller.signal.aborted) {
        showLoading("Downloading\u2026");
        const { data } = await downloadPdf({
          path: { aid: aid(), token: downloadToken },
          parseAs: "blob",
        });
        const blob = data as Blob;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${aid()}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        state.value = "done";
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      Notify.create({ type: "negative", message: "PDF export failed" });
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
