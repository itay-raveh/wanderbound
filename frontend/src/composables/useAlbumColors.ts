import { inject, provide, type ComputedRef, type InjectionKey } from "vue";

type Colors = Record<string, string>;

const KEY: InjectionKey<ComputedRef<Colors>> = Symbol("album-colors");

export function provideAlbumColors(colors: ComputedRef<Colors>): void {
  provide(KEY, colors);
}

export function useAlbumColors(): ComputedRef<Colors> {
  const colors = inject(KEY);
  if (!colors) throw new Error("useAlbumColors() called outside of AlbumViewer");
  return colors;
}
