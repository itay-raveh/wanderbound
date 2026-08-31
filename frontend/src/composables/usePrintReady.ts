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
