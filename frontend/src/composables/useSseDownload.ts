import { onScopeDispose, ref, type Ref } from "vue";
import { Loading, Notify } from "quasar";

export type SseStreamState = "idle" | "running" | "done" | "error";

export interface SseDownloadHandle {
  start(): void;
  abort(): void;
  state: Ref<SseStreamState>;
}

type EventAction = { loading: string } | { done: string } | { error: string };

type StringOrGetter = string | (() => string);
function resolve(v: StringOrGetter): string { return typeof v === "function" ? v() : v; }

interface SseDownloadConfig<T = unknown> {
  connect(signal: AbortSignal): Promise<AsyncIterable<T>>;
  onEvent(event: T): EventAction;
  downloadUrl(token: string): string;
  filename: StringOrGetter;
  errorMessage: StringOrGetter;
  initialMessage: StringOrGetter;
  loadingClass?: string;
}

const DONE_RESET_MS = 1500;

export function useSseDownload<T>(config: SseDownloadConfig<T>): SseDownloadHandle {
  const state = ref<SseStreamState>("idle");
  let controller: AbortController | null = null;
  let lastMsg = "";
  let resetTimer: ReturnType<typeof setTimeout> | null = null;

  function showLoading(message: string) {
    if (message === lastMsg) return;
    lastMsg = message;
    Loading.show({
      message,
      spinnerColor: "primary",
      ...(config.loadingClass && { customClass: config.loadingClass }),
    });
  }

  async function start() {
    if (state.value === "running") return;
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    controller = new AbortController();
    state.value = "running";
    showLoading(resolve(config.initialMessage));

    try {
      const stream = await config.connect(controller.signal);

      let downloadToken: string | null = null;

      for await (const raw of stream) {
        const action = config.onEvent(raw);
        if ("loading" in action) {
          showLoading(action.loading);
        } else if ("done" in action) {
          downloadToken = action.done;
        } else {
          state.value = "error";
          Notify.create({ type: "negative", message: action.error });
          return;
        }
      }

      if (!downloadToken || controller.signal.aborted) {
        if (!controller.signal.aborted) state.value = "error";
        return;
      }

      const a = document.createElement("a");
      a.href = config.downloadUrl(downloadToken);
      a.download = resolve(config.filename);
      a.click();
      state.value = "done";
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      Notify.create({ type: "negative", message: resolve(config.errorMessage) });
    } finally {
      Loading.hide();
      lastMsg = "";
      if (state.value === "done") {
        resetTimer = setTimeout(() => {
          state.value = "idle";
          resetTimer = null;
        }, DONE_RESET_MS);
      }
    }
  }

  function abort() {
    controller?.abort();
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    if (state.value === "running") state.value = "idle";
    Loading.hide();
    lastMsg = "";
  }

  onScopeDispose(() => abort());

  return { start: () => void start(), abort, state };
}
