import {
  inject,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";

export interface AlbumContext {
  albumId: Ref<string>;
  colors: ComputedRef<Record<string, string>>;
  orientations: ComputedRef<Record<string, string>>;
  tripStart: ComputedRef<string>;
  totalDays: ComputedRef<number>;
}

const KEY: InjectionKey<AlbumContext> = Symbol("album");

export function provideAlbum(ctx: AlbumContext): void {
  provide(KEY, ctx);
}

export function useAlbum(): AlbumContext {
  const ctx = inject(KEY);
  if (!ctx) throw new Error("useAlbum() called outside of AlbumViewer");
  return ctx;
}
