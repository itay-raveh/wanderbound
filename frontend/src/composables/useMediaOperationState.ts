import { shallowRef } from "vue";

export function useMediaOperationState<Phase>(
  idlePhase: Phase,
  errorPhase: Phase,
) {
  const phase = shallowRef<Phase>(idlePhase);
  const errorDetail = shallowRef<string | null>(null);
  let controller: AbortController | null = null;

  function begin(): AbortSignal {
    controller?.abort();
    controller = new AbortController();
    errorDetail.value = null;
    return controller.signal;
  }

  function fail(error: unknown, fallback: string): boolean {
    if (error instanceof DOMException && error.name === "AbortError") {
      return false;
    }
    phase.value = errorPhase;
    errorDetail.value = error instanceof Error ? error.message : fallback;
    return true;
  }

  function setError(message: string) {
    phase.value = errorPhase;
    errorDetail.value = message;
  }

  function abort() {
    controller?.abort();
    controller = null;
  }

  function clearError() {
    errorDetail.value = null;
  }

  function cancel() {
    abort();
    clearError();
    phase.value = idlePhase;
  }

  return {
    phase,
    errorDetail,
    begin,
    fail,
    setError,
    abort,
    clearError,
    cancel,
  };
}
