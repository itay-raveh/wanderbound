import {
  computed,
  inject,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";
import type { AlbumMedia } from "@/client";
import type { MediaResolutionWarningPreset } from "@/utils/photoQuality";
import { placementMediaUrl } from "@/utils/media";

interface AlbumProvide {
  albumId: Ref<string>;
  colors: ComputedRef<Record<string, string>>;
  media: ComputedRef<AlbumMedia[]>;
  tripStart: ComputedRef<string>;
  totalDays: ComputedRef<number>;
  mediaResolutionWarningPreset: ComputedRef<MediaResolutionWarningPreset>;
}

interface AlbumContext extends AlbumProvide {
  mediaByName: ComputedRef<Map<string, AlbumMedia>>;
  placementMediaUrl: (name: string) => string;
}

const KEY: InjectionKey<AlbumContext> = Symbol("album");

export function provideAlbum(ctx: AlbumProvide): AlbumContext {
  const mediaByName = computed(() => {
    const map = new Map<string, AlbumMedia>();
    for (const m of ctx.media.value) map.set(m.name, m);
    return map;
  });
  const albumCtx: AlbumContext = {
    ...ctx,
    mediaByName,
    placementMediaUrl: (name) =>
      placementMediaUrl(
        name,
        ctx.albumId.value,
        mediaByName.value.get(name),
      ),
  };
  provide(KEY, albumCtx);
  return albumCtx;
}

export function useAlbum(): AlbumContext {
  const ctx = inject(KEY);
  if (!ctx) throw new Error("useAlbum() called outside of AlbumViewer");
  return ctx;
}
