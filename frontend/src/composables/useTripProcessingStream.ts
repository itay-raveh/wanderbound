import { ref, type Ref } from "vue";
import {
  processUser,
  type ErrorData,
  type PhaseUpdate,
  type ProcessingPhase,
  type TripStart,
} from "@/client";
import { t } from "@/i18n";

export type ProcessingState = "idle" | "running" | "done" | "error";

interface PhaseProgress {
  done: number;
  total: number;
}

export type PhaseDone = Record<ProcessingPhase, PhaseProgress>;

export const PHASE_ORDER: ProcessingPhase[] = [
  "elevations",
  "weather",
  "layouts",
];

interface UseTripProcessingStream {
  start(): void;
  abort(): void;
  state: Ref<ProcessingState>;
  tripIndex: Ref<number>;
  phaseDone: Ref<PhaseDone>;
  errorDetail: Ref<string | null>;
}

/** hey-api types SSE stream items as Array<union>, but yields individual events. */
type ProcessingEvent =
  | ({ type: "trip_start" } & TripStart)
  | ({ type: "phase" } & PhaseUpdate)
  | ({ type: "error" } & ErrorData);

function freshPhaseDone(): PhaseDone {
  return Object.fromEntries(
    PHASE_ORDER.map((p) => [p, { done: 0, total: 0 }]),
  ) as PhaseDone;
}

export function useTripProcessingStream(): UseTripProcessingStream {
  const state = ref<ProcessingState>("idle");
  const tripIndex = ref(0);
  const phaseDone = ref<PhaseDone>(freshPhaseDone());
  const errorDetail = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start() {
    controller = new AbortController();
    state.value = "running";
    tripIndex.value = 0;
    phaseDone.value = freshPhaseDone();
    errorDetail.value = null;

    try {
      const { stream } = await processUser({
        signal: controller.signal,
        sseMaxRetryAttempts: 1,
        throwOnError: true,
      });

      for await (const raw of stream) {
        const event = raw as unknown as ProcessingEvent;
        switch (event.type) {
          case "trip_start":
            tripIndex.value = event.trip_index;
            phaseDone.value = freshPhaseDone();
            break;
          case "phase":
            phaseDone.value[event.phase] = {
              done: event.done,
              total: event.total,
            };
            break;
          case "error":
            state.value = "error";
            errorDetail.value = t("error.processingFailed");
            return;
        }
      }

      if (!controller?.signal.aborted) state.value = "done";
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      errorDetail.value = t("error.connectionFailed");
    }
  }

  function abort() {
    controller?.abort();
    state.value = "idle";
    tripIndex.value = 0;
    phaseDone.value = freshPhaseDone();
    errorDetail.value = null;
  }

  return {
    start: () => void start(),
    abort,
    state,
    tripIndex,
    phaseDone,
    errorDetail,
  };
}
