import { inject, type InjectionKey } from "vue";

export interface PanoramaFrameRequest {
  media: string;
  aspectRatio: number;
  showSeam?: boolean;
}

export const PANORAMA_FRAME_KEY: InjectionKey<
  (request: PanoramaFrameRequest) => void
> = Symbol("panorama-frame");

export function usePanoramaFrame() {
  return inject(PANORAMA_FRAME_KEY, null);
}
