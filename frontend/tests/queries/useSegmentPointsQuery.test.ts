import { flushPromises } from "@vue/test-utils";
import { PiniaColada } from "@pinia/colada";
import { createPinia } from "pinia";
import { http, HttpResponse } from "msw";
import { createApp, computed, defineComponent, h, ref } from "vue";
import type { Ref } from "vue";
import { server } from "../mocks/server";
import { BASE } from "../mocks/handlers";
import { makeSegment } from "../helpers";
import { provideAlbum } from "@/composables/useAlbum";
import {
  ROUTE_REFETCH_LIMIT,
  ROUTE_REFETCH_MS,
  useSegmentPointsQuery,
} from "@/queries/useSegmentPointsQuery";
import type { Segment } from "@/client";

function mountQuery(fromTime: Ref<number> = ref(0), toTime: Ref<number> = ref(100)) {
  let result!: ReturnType<typeof useSegmentPointsQuery>;
  const Child = defineComponent({
    setup() {
      result = useSegmentPointsQuery(fromTime, toTime);
      return () => null;
    },
  });
  const Parent = defineComponent({
    setup() {
      provideAlbum({
        albumId: ref("aid-1"),
        colors: computed(() => ({})),
        media: computed(() => []),
        tripStart: computed(() => "2024-01-01T00:00:00Z"),
        totalDays: computed(() => 1),
        upgradedMedia: computed(() => new Set<string>()),
      });
      return () => h(Child);
    },
  });
  const app = createApp(Parent);
  app.use(createPinia());
  app.use(PiniaColada);
  app.mount(document.createElement("div"));
  onTestFinished(() => app.unmount());

  return { query: result, unmount: () => app.unmount() };
}

describe("useSegmentPointsQuery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("refetches about every minute while driving routes are missing", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        return HttpResponse.json([
          makeSegment({ kind: "driving", route: null }),
        ] satisfies Segment[]);
      }),
    );

    mountQuery();
    await flushPromises();
    expect(calls).toBe(1);

    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    await flushPromises();

    expect(calls).toBe(2);
  });

  it("does not refetch when all matchable segments have routes", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        return HttpResponse.json([
          makeSegment({ kind: "walking", route: [[1, 2]] }),
          makeSegment({ kind: "driving", route: [[3, 4]] }),
        ] satisfies Segment[]);
      }),
    );

    mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    await flushPromises();

    expect(calls).toBe(1);
  });

  it("does not refetch for hike and flight segments without routes", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        return HttpResponse.json([
          makeSegment({ kind: "hike", route: null }),
          makeSegment({ kind: "flight", route: null }),
        ] satisfies Segment[]);
      }),
    );

    mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    await flushPromises();

    expect(calls).toBe(1);
  });

  it("stops polling after the route refetch cap", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        return HttpResponse.json([
          makeSegment({ kind: "walking", route: null }),
        ] satisfies Segment[]);
      }),
    );

    mountQuery();
    await flushPromises();

    for (let i = 0; i < ROUTE_REFETCH_LIMIT + 1; i += 1) {
      await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
      await flushPromises();
    }

    expect(calls).toBe(1 + ROUTE_REFETCH_LIMIT);
  });

  it("resets the route refetch cap when the query range changes", async () => {
    const fromTime = ref(0);
    const toTime = ref(100);
    let calls = 0;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        return HttpResponse.json([
          makeSegment({ kind: "driving", route: null }),
        ] satisfies Segment[]);
      }),
    );

    mountQuery(fromTime, toTime);
    await flushPromises();
    for (let i = 0; i < ROUTE_REFETCH_LIMIT + 1; i += 1) {
      await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
      await flushPromises();
    }
    expect(calls).toBe(1 + ROUTE_REFETCH_LIMIT);

    fromTime.value = 100;
    toTime.value = 200;
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    await flushPromises();

    expect(calls).toBe(3 + ROUTE_REFETCH_LIMIT);
  });

  it("does not start another refetch while the previous one is loading", async () => {
    let calls = 0;
    let resolveSecond: (() => void) | undefined;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json([
            makeSegment({ kind: "driving", route: null }),
          ] satisfies Segment[]);
        }
        return new Promise((resolve) => {
          resolveSecond = () =>
            resolve(
              HttpResponse.json([
                makeSegment({ kind: "driving", route: null }),
              ] satisfies Segment[]),
            );
        });
      }),
    );

    mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls).toBe(2);

    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls).toBe(2);

    resolveSecond?.();
    await flushPromises();
  });

  it("does not schedule another poll after unmounting during a refetch", async () => {
    let calls = 0;
    let resolveSecond: (() => void) | undefined;
    server.use(
      http.get(`${BASE}/albums/:aid/segments/points`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json([
            makeSegment({ kind: "driving", route: null }),
          ] satisfies Segment[]);
        }
        return new Promise((resolve) => {
          resolveSecond = () =>
            resolve(
              HttpResponse.json([
                makeSegment({ kind: "driving", route: null }),
              ] satisfies Segment[]),
            );
        });
      }),
    );

    const { unmount } = mountQuery();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);
    expect(calls).toBe(2);

    unmount();
    resolveSecond?.();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUTE_REFETCH_MS);

    expect(calls).toBe(2);
  });
});
