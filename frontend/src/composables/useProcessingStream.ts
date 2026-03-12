import { ref, type Ref } from "vue";
import { processUser } from "@/client";
import type { ProgressData } from "@/client/types.gen";

export type StreamState = "idle" | "running" | "done" | "error";

export interface UseProcessingStream {
  start(): void;
  abort(): void;
  state: Ref<StreamState>;
  progress: Ref<ProgressData | null>;
  errorDetail: Ref<string | null>;
}

type RawSseEvent = { type: string; detail?: string } & Record<
  string,
  unknown
>;

export function useProcessingStream(): UseProcessingStream {
  const state = ref<StreamState>("idle");
  const progress = ref<ProgressData | null>(null);
  const errorDetail = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start() {
    controller = new AbortController();
    state.value = "running";
    progress.value = null;
    errorDetail.value = null;

    try {
      const { stream } = await processUser({
        signal: controller.signal,
        sseMaxRetryAttempts: 1,
        throwOnError: true,
      });

      for await (const raw of stream) {
        const event = raw as unknown as RawSseEvent;
        switch (event.type) {
          case "progress":
            progress.value = event as unknown as ProgressData;
            break;
          case "done":
            state.value = "done";
            return;
          case "error":
            state.value = "error";
            errorDetail.value = event.detail ?? "Processing failed";
            return;
        }
      }

      // Stream ended without done/error
      if (state.value === "running") {
        state.value = "error";
        errorDetail.value = "Connection lost. Please try again.";
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      errorDetail.value = "Connection failed. Please try again.";
    }
  }

  function abort() {
    controller?.abort();
    state.value = "idle";
    progress.value = null;
    errorDetail.value = null;
  }

  return { start: () => void start(), abort, state, progress, errorDetail };
}
