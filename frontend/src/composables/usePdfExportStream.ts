import { ref, computed, type Ref, type ComputedRef } from "vue";
import { Dark, Notify } from "quasar";
import { generatePdf, downloadPdf } from "@/client";

export type PdfStreamState = "idle" | "queued" | "running" | "done" | "error";
type Phase = "loading" | "rendering" | "merging";

type RawSseEvent = { type: string } & Record<string, unknown>;

const PHASE_LABELS: Record<Phase, string> = {
  loading: "Loading album…",
  rendering: "Rendering",
  merging: "Merging…",
};

export interface UsePdfExportStream {
  start(): void;
  abort(): void;
  state: Ref<PdfStreamState>;
  buttonLabel: ComputedRef<string>;
  progress: ComputedRef<number>;
}

export function usePdfExportStream(aid: () => string): UsePdfExportStream {
  const state = ref<PdfStreamState>("idle");
  const phase = ref<Phase>("loading");
  const done = ref(0);
  const total = ref(0);
  let controller: AbortController | null = null;

  const buttonLabel = computed(() => {
    switch (state.value) {
      case "queued":
        return "Queued…";
      case "running":
        if (phase.value === "rendering" && total.value > 1) {
          return `${PHASE_LABELS[phase.value]} ${done.value}/${total.value}…`;
        }
        return PHASE_LABELS[phase.value];
      default:
        return "Export PDF";
    }
  });

  const progress = computed(() => {
    if (state.value !== "running" || total.value === 0) return 0;
    return done.value / total.value;
  });

  async function start() {
    controller = new AbortController();
    state.value = "queued";
    phase.value = "loading";
    done.value = 0;
    total.value = 0;

    try {
      const { stream } = await generatePdf({
        path: { aid: aid() },
        query: { dark: Dark.isActive },
        signal: controller.signal,
        sseMaxRetryAttempts: 0,
      });

      let downloadToken: string | null = null;

      for await (const raw of stream) {
        const event = raw as unknown as RawSseEvent;
        switch (event.type) {
          case "queued":
            state.value = "queued";
            break;
          case "progress":
            state.value = "running";
            phase.value = event.phase as Phase;
            done.value = event.done as number;
            total.value = event.total as number;
            break;
          case "done":
            downloadToken = event.token as string;
            break;
          case "error":
            state.value = "error";
            Notify.create({ type: "negative", message: (event.detail as string) ?? "PDF export failed" });
            return;
        }
      }

      if (downloadToken && !controller.signal.aborted) {
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
  }

  return {
    start: () => void start(),
    abort,
    state,
    buttonLabel,
    progress,
  };
}
