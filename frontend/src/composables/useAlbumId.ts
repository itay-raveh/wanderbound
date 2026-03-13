import { inject, provide, type InjectionKey, type Ref } from "vue";

const KEY: InjectionKey<Ref<string>> = Symbol("album-id");

export function provideAlbumId(albumId: Ref<string>): void {
  provide(KEY, albumId);
}

export function useAlbumId(): Ref<string> {
  const id = inject(KEY);
  if (!id) throw new Error("useAlbumId() called outside of AlbumViewer");
  return id;
}
