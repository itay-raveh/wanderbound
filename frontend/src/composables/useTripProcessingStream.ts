import { ref, type Ref } from "vue";
import {
  processUser,
  type ProcessUserResponse,
  type ProcessingPhase,
} from "@/client";
import { t } from "@/i18n";

export type ProcessingState = "idle" | "running" | "done" | "error";
export type { ProcessingPhase };

export interface SegmentSummary {
  hikes: number;
  walks: number;
  drives: number;
  flights: number;
}

interface PhaseProgress {
  done: number;
  total: number;
}

export type PhaseDone = Record<ProcessingPhase, PhaseProgress>;

export const PHASE_ORDER: ProcessingPhase[] = [
  "elevations",
  "weather",
  "segments",
  "layouts",
];

interface UseTripProcessingStream {
  start(): void;
  abort(): void;
  state: Ref<ProcessingState>;
  tripIndex: Ref<number>;
  phaseDone: Ref<PhaseDone>;
  segmentSummary: Ref<SegmentSummary>;
  errorDetail: Ref<string | null>;
}

/** hey-api types SSE stream items as an array union, but yields individual events. */
type ProcessingEvent = ProcessUserResponse[number];

function freshPhaseDone(): PhaseDone {
  return Object.fromEntries(
    PHASE_ORDER.map((p) => [p, { done: 0, total: 0 }]),
  ) as PhaseDone;
}

function freshSegmentSummary(): SegmentSummary {
  return { hikes: 0, walks: 0, drives: 0, flights: 0 };
}

export function useTripProcessingStream(): UseTripProcessingStream {
  const state = ref<ProcessingState>("idle");
  const tripIndex = ref(0);
  const phaseDone = ref<PhaseDone>(freshPhaseDone());
  const segmentSummary = ref<SegmentSummary>(freshSegmentSummary());
  const errorDetail = ref<string | null>(null);
  let controller: AbortController | null = null;

  async function start() {
    controller = new AbortController();
    state.value = "running";
    tripIndex.value = 0;
    phaseDone.value = freshPhaseDone();
    segmentSummary.value = freshSegmentSummary();
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
          case "segments_found":
            segmentSummary.value = {
              hikes: segmentSummary.value.hikes + event.hikes,
              walks: segmentSummary.value.walks + event.walks,
              drives: segmentSummary.value.drives + event.drives,
              flights: segmentSummary.value.flights + event.flights,
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
    segmentSummary.value = freshSegmentSummary();
    errorDetail.value = null;
  }

  return {
    start: () => void start(),
    abort,
    state,
    tripIndex,
    phaseDone,
    segmentSummary,
    errorDetail,
  };
}
