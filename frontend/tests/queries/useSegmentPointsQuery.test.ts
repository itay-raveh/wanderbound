import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { ref } from "vue";
import type { Ref } from "vue";
import { server } from "../mocks/server";
import { BASE } from "../mocks/handlers";
import {
  deferred,
  makeSegment,
  provideTestAlbum,
  withParentSetup,
} from "../helpers";
import {
  ROUTE_REFETCH_LIMIT,
  ROUTE_REFETCH_MS,
  useSegmentPointsQuery,
} from "@/queries/useSegmentPointsQuery";
import type { Segment } from "@/client";

type SegmentHandlerResult = Segment[] | Promise<Response>;

function mountQuery(
  fromTime: Ref<number> = ref(0),
  toTime: Ref<number> = ref(100),
) {
  const { result: query, unmount } = withParentSetup(
    () => {
      provideTestAlbum({ albumId: "aid-1" });
    },
    () => useSegmentPointsQuery(fromTime, toTime),
  );

  return { query, unmount };
}

function mockSegmentPoints(handler: (calls: number) => SegmentHandlerResult) {
  let calls = 0;
  server.use(
    http.get(`${BASE}/albums/:aid/segments/points`, () => {
      calls += 1;
      const result = handler(calls);
      return result instanceof Promise ? result : HttpResponse.json(result);
    }),
  );
  return () => calls;
}

const missingDrivingRoute = () =>
  [makeSegment({ kind: "driving", route: null })] satisfies Segment[];

async function advanceRoutePoll() {
  await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
  await flushPromises();
}

describe("useSegmentPointsQuery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("refetches about every minute while driving routes are missing", async () => {
    const calls = mockSegmentPoints(missingDrivingRoute);

    mountQuery();
    await flushPromises();
    expect(calls()).toBe(1);

    await advanceRoutePoll();

    expect(calls()).toBe(2);
  });

  it("does not refetch when all matchable segments have routes", async () => {
    const calls = mockSegmentPoints(
      () =>
        [
          makeSegment({ kind: "walking", route: [[1, 2]] }),
          makeSegment({ kind: "driving", route: [[3, 4]] }),
        ] satisfies Segment[],
    );

    mountQuery();
    await flushPromises();
    await advanceRoutePoll();

    expect(calls()).toBe(1);
  });

  it("does not refetch for hike and flight segments without routes", async () => {
    const calls = mockSegmentPoints(
      () =>
        [
          makeSegment({ kind: "hike", route: null }),
          makeSegment({ kind: "flight", route: null }),
        ] satisfies Segment[],
    );

    mountQuery();
    await flushPromises();
    await advanceRoutePoll();

    expect(calls()).toBe(1);
  });

  it("stops polling after the route refetch cap", async () => {
    const calls = mockSegmentPoints(
      () => [makeSegment({ kind: "walking", route: null })] satisfies Segment[],
    );

    mountQuery();
    await flushPromises();

    for (let i = 0; i < ROUTE_REFETCH_LIMIT + 1; i += 1) {
      await advanceRoutePoll();
    }

    expect(calls()).toBe(1 + ROUTE_REFETCH_LIMIT);
  });

  it("resets the route refetch cap when the query range changes", async () => {
    const fromTime = ref(0);
    const toTime = ref(100);
    const calls = mockSegmentPoints(missingDrivingRoute);

    mountQuery(fromTime, toTime);
    await flushPromises();
    for (let i = 0; i < ROUTE_REFETCH_LIMIT + 1; i += 1) {
      await advanceRoutePoll();
    }
    expect(calls()).toBe(1 + ROUTE_REFETCH_LIMIT);

    fromTime.value = 100;
    toTime.value = 200;
    await flushPromises();
    await advanceRoutePoll();

    expect(calls()).toBe(3 + ROUTE_REFETCH_LIMIT);
  });

  it("does not start another refetch while the previous one is loading", async () => {
    const secondResponse = deferred<Response>();
    const calls = mockSegmentPoints((call) => {
      if (call === 1) {
        return missingDrivingRoute();
      }
      return secondResponse.promise;
    });

    mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls()).toBe(2);

    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls()).toBe(2);

    secondResponse.resolve(HttpResponse.json(missingDrivingRoute()));
    await flushPromises();
  });

  it("does not schedule another poll after unmounting during a refetch", async () => {
    const secondResponse = deferred<Response>();
    const calls = mockSegmentPoints((call) => {
      if (call === 1) {
        return missingDrivingRoute();
      }
      return secondResponse.promise;
    });

    const { unmount } = mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls()).toBe(2);

    unmount();
    secondResponse.resolve(HttpResponse.json(missingDrivingRoute()));
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);

    expect(calls()).toBe(2);
  });
});
