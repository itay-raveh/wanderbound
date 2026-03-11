import { inject, provide, type InjectionKey } from "vue";

const KEY: InjectionKey<true> = Symbol("print-mode");

/** Call in AlbumViewer when printMode is true. */
export function providePrintMode(): void {
  provide(KEY, true);
}

/** Returns true when inside a print-mode AlbumViewer, false otherwise. */
export function usePrintMode(): boolean {
  return inject(KEY, false) === true;
}
