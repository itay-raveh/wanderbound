import { ref, type Ref } from "vue";
import { processUser, type ProcessingPhase } from "@/client";

export type { ProcessingPhase };

export type StreamState = "idle" | "running" | "done" | "error";

export interface UseProcessingStream {
  start(): void;
  abort(): void;
  state: Ref<StreamState>;
  tripIndex: Ref<number>;
  phase: Ref<ProcessingPhase | null>;
  phaseDone: Ref<number>;
  errorDetail: Ref<string | null>;
}

type RawSseEvent = { type: string } & Record<string, unknown>;

export function useProcessingStream(): UseProcessingStream {
  const state = ref<StreamState>("idle");
  const tripIndex = ref(0);
  const phase = ref<ProcessingPhase | null>(null);
  const phaseDone = ref(0);
  const errorDetail = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start() {
    controller = new AbortController();
    state.value = "running";
    tripIndex.value = 0;
    phase.value = null;
    phaseDone.value = 0;
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
          case "trip_start":
            tripIndex.value = event.trip_index as number;
            phase.value = null;
            phaseDone.value = 0;
            break;
          case "phase":
            phase.value = event.phase as ProcessingPhase;
            phaseDone.value = event.done as number;
            break;
          case "error":
            state.value = "error";
            errorDetail.value = (event.detail as string) ?? "Processing failed";
            return;
        }
      }

      state.value = "done";
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      errorDetail.value = "Connection failed. Please try again.";
    }
  }

  function abort() {
    controller?.abort();
    state.value = "idle";
    phase.value = null;
    phaseDone.value = 0;
    errorDetail.value = null;
  }

  return {
    start: () => void start(),
    abort,
    state,
    tripIndex,
    phase,
    phaseDone,
    errorDetail,
  };
}
