import {
  computed,
  inject,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";
import type { Media } from "@/client";

interface AlbumProvide {
  albumId: Ref<string>;
  colors: ComputedRef<Record<string, string>>;
  media: ComputedRef<Media[]>;
  tripStart: ComputedRef<string>;
  totalDays: ComputedRef<number>;
  photosConnected?: ComputedRef<boolean>;
}

interface AlbumContext extends Omit<AlbumProvide, "photosConnected"> {
  mediaByName: ComputedRef<Map<string, Media>>;
  photosConnected: ComputedRef<boolean>;
}

const KEY: InjectionKey<AlbumContext> = Symbol("album");

const PHOTOS_NOT_CONNECTED = computed(() => false);

export function provideAlbum(ctx: AlbumProvide): AlbumContext {
  const mediaByName = computed(() => {
    const map = new Map<string, Media>();
    for (const m of ctx.media.value) map.set(m.name, m);
    return map;
  });
  const albumCtx: AlbumContext = {
    ...ctx,
    mediaByName,
    photosConnected: ctx.photosConnected ?? PHOTOS_NOT_CONNECTED,
  };
  provide(KEY, albumCtx);
  return albumCtx;
}

export function useAlbum(): AlbumContext {
  const ctx = inject(KEY);
  if (!ctx) throw new Error("useAlbum() called outside of AlbumViewer");
  return ctx;
}
