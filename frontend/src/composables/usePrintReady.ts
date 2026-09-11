import {
  inject,
  provide,
  readonly,
  ref,
  type InjectionKey,
  type Ref,
} from "vue";
import { z } from "zod";

const KEY: InjectionKey<true> = Symbol("print-mode");
const MAP_PIXEL_RATIO_KEY: InjectionKey<number> = Symbol(
  "print-map-pixel-ratio",
);
const MEDIA_READY_KEY: InjectionKey<Readonly<Ref<boolean>>> =
  Symbol("print-media-ready");
const MEDIA_READY_DEFAULT = readonly(ref(true));
const DEFAULT_PRINT_TIMEOUT_MS = 900_000;
const positiveNumber = z.number().positive();
const printTimeout = positiveNumber.catch(DEFAULT_PRINT_TIMEOUT_MS);
const printCpuCount = positiveNumber
  .transform(Math.floor)
  .optional()
  .catch(undefined);

type PrintRuntimeWindow = Window & {
  __PRINT_CPU_COUNT__?: unknown;
  __PRINT_TIMEOUT_MS__?: unknown;
};

export function getPrintTimeoutMs(): number {
  return printTimeout.parse(
    (window as PrintRuntimeWindow).__PRINT_TIMEOUT_MS__,
  );
}

export function getPrintCpuCount(): number | undefined {
  return printCpuCount.parse(
    (window as PrintRuntimeWindow).__PRINT_CPU_COUNT__,
  );
}

/** Call in AlbumViewer when printMode is true. */
export function providePrintMode(mapPixelRatio = 2): void {
  provide(KEY, true);
  provide(MAP_PIXEL_RATIO_KEY, mapPixelRatio);
}

export function usePrintMapPixelRatio(): number {
  return inject(MAP_PIXEL_RATIO_KEY, 2);
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

type PrintMapState = "loading" | "ready" | "error";
const MAP_STATE_KEY: InjectionKey<Ref<PrintMapState>> =
  Symbol("print-map-state");

export function providePrintMapState(): Ref<PrintMapState> {
  const state = ref<PrintMapState>("loading");
  provide(MAP_STATE_KEY, state);
  return state;
}

export function usePrintMapState(): Ref<PrintMapState> | null {
  return inject(MAP_STATE_KEY, null);
}
