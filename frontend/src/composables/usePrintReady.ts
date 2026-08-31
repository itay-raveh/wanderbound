import {
  inject,
  provide,
  readonly,
  ref,
  type InjectionKey,
  type Ref,
} from "vue";

const KEY: InjectionKey<true> = Symbol("print-mode");
const MEDIA_READY_KEY: InjectionKey<Readonly<Ref<boolean>>> =
  Symbol("print-media-ready");
const MEDIA_READY_DEFAULT = readonly(ref(true));
const DEFAULT_PRINT_TIMEOUT_MS = 900_000;

type PrintRuntimeWindow = Window & {
  __PRINT_CPU_COUNT__?: unknown;
  __PRINT_TIMEOUT_MS__?: unknown;
};

export function getPrintTimeoutMs(): number {
  const value = (window as PrintRuntimeWindow).__PRINT_TIMEOUT_MS__;
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : DEFAULT_PRINT_TIMEOUT_MS;
}

export function getPrintCpuCount(): number | undefined {
  const value = (window as PrintRuntimeWindow).__PRINT_CPU_COUNT__;
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : undefined;
}

/** Call in AlbumViewer when printMode is true. */
export function providePrintMode(): void {
  provide(KEY, true);
}

export function usePrintMode(): boolean {
  return inject(KEY, false) === true;
}

export function providePrintMediaReady(ready: Ref<boolean>): void {
  provide(MEDIA_READY_KEY, readonly(ready));
}

export function usePrintMediaReady(): Readonly<Ref<boolean>> {
  return inject(MEDIA_READY_KEY, MEDIA_READY_DEFAULT);
}
