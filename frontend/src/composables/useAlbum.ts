import {
  computed,
  inject,
  provide,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from "vue";
import type { Media } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";

interface AlbumProvide {
  albumId: Ref<string>;
  colors: ComputedRef<Record<string, string>>;
  media: ComputedRef<Media[]>;
  tripStart: ComputedRef<string>;
  totalDays: ComputedRef<number>;
}

interface AlbumContext extends AlbumProvide {
  mediaByName: ComputedRef<Map<string, Media>>;
  photosConnected: ComputedRef<boolean>;
}

const KEY: InjectionKey<AlbumContext> = Symbol("album");

export function provideAlbum(ctx: AlbumProvide): AlbumContext {
  const { user } = useUserQuery();
  const photosConnected = computed(
    () => !!user.value?.google_photos_connected_at,
  );
  const mediaByName = computed(() => {
    const map = new Map<string, Media>();
    for (const m of ctx.media.value) map.set(m.name, m);
    return map;
  });
  const albumCtx: AlbumContext = { ...ctx, mediaByName, photosConnected };
  provide(KEY, albumCtx);
  return albumCtx;
}

export function useAlbum(): AlbumContext {
  const ctx = inject(KEY);
  if (!ctx) throw new Error("useAlbum() called outside of AlbumViewer");
  return ctx;
}
