import { useQuery } from "@pinia/colada";
import {
  markRaw,
  onScopeDispose,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";
import { readSegmentPoints, type Segment } from "@/client";
import { queryKeys, STALE_TIME } from "./keys";
import { useAlbum } from "@/composables/useAlbum";

export const ROUTE_REFETCH_MS = 60_000;
export const ROUTE_REFETCH_LIMIT = 10;

function hasUnmatchedRoute(segments: Segment[] | undefined): boolean {
  return !!segments?.some(
    (segment) =>
      (segment.kind === "driving" || segment.kind === "walking") &&
      segment.route == null,
  );
}

export function useSegmentPointsQuery(
  fromTime: Ref<number>,
  toTime: Ref<number>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const { albumId } = useAlbum();

  const query = useQuery({
    key: () =>
      queryKeys.segmentPoints(albumId.value, fromTime.value, toTime.value),
    query: async () => {
      const { data } = await readSegmentPoints({
        path: { aid: albumId.value },
        query: { from_time: fromTime.value, to_time: toTime.value },
      });
      return markRaw(data);
    },
    staleTime: STALE_TIME,
    enabled,
  });

  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempts = 0;
  let disposed = false;
  let lastPollingKey = "";

  function clearTimer() {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  function schedule() {
    clearTimer();
    const pollingKey = queryKeys
      .segmentPoints(albumId.value, fromTime.value, toTime.value)
      .join(":");
    if (pollingKey !== lastPollingKey) {
      lastPollingKey = pollingKey;
      attempts = 0;
    }
    if (
      disposed ||
      !toValue(enabled) ||
      !hasUnmatchedRoute(query.data.value) ||
      attempts >= ROUTE_REFETCH_LIMIT
    )
      return;

    timer = setTimeout(() => {
      if (query.asyncStatus.value === "loading") {
        schedule();
        return;
      }
      attempts += 1;
      void query.refetch().finally(schedule);
    }, ROUTE_REFETCH_MS);
  }

  watch(
    [query.data, () => toValue(enabled)],
    () => {
      if (!hasUnmatchedRoute(query.data.value)) attempts = 0;
      schedule();
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    disposed = true;
    clearTimer();
  });

  return query;
}
