import { inject, provide, type ComputedRef, type InjectionKey } from "vue";

interface TripProgress {
  tripStart: ComputedRef<string>;
  totalDays: ComputedRef<number>;
}

const KEY: InjectionKey<TripProgress> = Symbol("trip-progress");

export function provideTripProgress(progress: TripProgress): void {
  provide(KEY, progress);
}

export function useTripProgress(): TripProgress {
  const ctx = inject(KEY);
  if (!ctx) throw new Error("useTripProgress() called outside of AlbumViewer");
  return ctx;
}
