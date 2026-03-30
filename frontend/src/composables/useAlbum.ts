import {
  inject,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";
import type { Media } from "@/client";

interface AlbumContext {
  albumId: Ref<string>;
  colors: ComputedRef<Record<string, string>>;
  media: ComputedRef<Media[]>;
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
