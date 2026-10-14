import type { z } from "zod";
import { useTimeoutFn } from "@vueuse/core";
import { onScopeDispose, ref, toValue, type Ref } from "vue";
import { Loading, Notify } from "quasar";

type ExportState = "idle" | "running" | "done" | "error";

export interface PolledExportHandle {
  start(): void;
  abort(): void;
  state: Ref<ExportState>;
}

type EventAction =
  | { loading: string }
  | { done: string }
  | { error: string }
  | { info: string };

type StringOrGetter = string | (() => string);

interface PolledExportConfig<T = unknown> {
  schema: z.ZodType<T>;
  connect(signal: AbortSignal): Promise<AsyncIterable<unknown>>;
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
    showLoading(toValue(config.initialMessage));

    try {
      const stream = await config.connect(controller.signal);

      let downloadToken: string | null = null;

      for await (const raw of stream) {
        const action = config.onEvent(config.schema.parse(raw));
        if ("loading" in action) {
          showLoading(action.loading);
        } else if ("done" in action) {
          downloadToken = action.done;
        } else if ("error" in action) {
          state.value = "error";
          Notify.create({ type: "negative", message: action.error });
          return;
        } else {
          state.value = "idle";
          Notify.create({ type: "info", message: action.info });
          return;
        }
      }

      if (!downloadToken || controller.signal.aborted) {
        if (!controller.signal.aborted) state.value = "error";
        return;
      }

      const a = document.createElement("a");
      a.href = config.downloadUrl(downloadToken);
      a.download = toValue(config.filename);
      a.click();
      state.value = "done";
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      state.value = "error";
      Notify.create({
        type: "negative",
        message: toValue(config.errorMessage),
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
