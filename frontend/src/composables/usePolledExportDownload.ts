import { useTimeoutFn } from "@vueuse/core";
import { onScopeDispose, ref, type Ref } from "vue";
import { Loading, Notify } from "quasar";

export type ExportState = "idle" | "running" | "done" | "error";

export interface PolledExportHandle {
  start(): void;
  abort(): void;
  state: Ref<ExportState>;
}

type EventAction = { loading: string } | { done: string } | { error: string };

type StringOrGetter = string | (() => string);
function resolve(v: StringOrGetter): string {
  return typeof v === "function" ? v() : v;
}

interface PolledExportConfig<T = unknown> {
  connect(signal: AbortSignal): Promise<AsyncIterable<T>>;
  onEvent(event: T): EventAction;
  downloadUrl(token: string): string;
  filename: StringOrGetter;
  errorMessage: StringOrGetter;
  initialMessage: StringOrGetter;
  /** Skip Quasar Loading overlay - caller renders its own progress UI. */
  headless?: boolean;
}

const DONE_RESET_MS = 1500;

export function usePolledExportDownload<T>(
  config: PolledExportConfig<T>,
): PolledExportHandle {
  const state = ref<ExportState>("idle");
  let controller: AbortController | null = null;
  let lastMsg = "";
  const { start: armReset, stop: cancelReset } = useTimeoutFn(
    () => {
      state.value = "idle";
    },
    DONE_RESET_MS,
    { immediate: false },
  );

  function showLoading(message: string) {
    if (message === lastMsg) return;
    lastMsg = message;
    if (config.headless) return;
    Loading.show({
      message,
      spinnerColor: "primary",
    });
  }

  async function start() {
    if (state.value === "running") return;
    cancelReset();
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
      Notify.create({
        type: "negative",
        message: resolve(config.errorMessage),
      });
    } finally {
      if (!config.headless) Loading.hide();
      lastMsg = "";
      if (state.value === "done") armReset();
    }
  }

  function abort() {
    controller?.abort();
    cancelReset();
    if (state.value === "running" || state.value === "done")
      state.value = "idle";
    if (!config.headless) Loading.hide();
    lastMsg = "";
  }

  onScopeDispose(() => abort());

  return { start: () => void start(), abort, state };
}
