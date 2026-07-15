import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ref, type Ref } from "vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import { mountWithPlugins, makeStep } from "../helpers";
import type { AlbumMeta } from "@/client";
import { useActiveSection } from "@/composables/useActiveSection";

type TestVirtualItem = {
  key: string;
  index: number;
  start: number;
  size: number;
  end: number;
};

let virtualItems: Ref<TestVirtualItem[]>;
let scrollToIndex: ReturnType<typeof vi.fn>;
let measurements: Array<{ start: number }>;

vi.mock("@/composables/useWindowVirtualizer", () => ({
  useWindowVirtualizer: () => ({
    virtualizer: {
      scrollState: null,
      getMeasurements: () => measurements,
      scrollToIndex,
    },
    items: virtualItems,
    size: ref(2365),
    version: ref(0),
  }),
}));

vi.mock("@/components/album/map/HikeMapPage.vue", () => ({
  default: { template: '<div class="hike-map" />' },
}));

function makeAlbum(): AlbumMeta {
  return {
    uid: 1,
    id: "album-1",
    hidden_headers: ["cover-front", "cover-back", "overview"],
    hidden_steps: [],
    maps_ranges: [],
    chapters: [
      {
        id: "chapter-1",
        title: "Album",
        subtitle: "",
        step_ids: [1],
        front_cover_photo: "",
        back_cover_photo: "",
      },
    ],
    colors: {},
  };
}

beforeEach(() => {
  useActiveSection().resetActiveSection();
  scrollToIndex = vi.fn();
  measurements = [{ start: 0 }];
  virtualItems = ref([
    {
      key: "chapter-chapter-1-full-map",
      index: 0,
      start: 0,
      size: 2365,
      end: 2365,
    },
  ]);
});

describe("AlbumViewer", () => {
  test("jumps instantly when a chapter target measurement is stale", () => {
    measurements = [];
    const album = makeAlbum();
    album.hidden_headers = ["cover-back", "overview", "full-map"];
    const wrapper = mountWithPlugins(AlbumViewer, {
      props: {
        album,
        media: [],
        steps: [makeStep()],
        segmentOutlines: [],
      },
    });

    const scrolled = useActiveSection().scrollToSection(
      "chapter-chapter-1-cover-front",
    );

    expect(scrolled).toBe(true);
    expect(scrollToIndex).toHaveBeenCalledWith(0, {
      align: "start",
      behavior: "instant",
    });
    wrapper.unmount();
  });

  test("reserves virtual item height when heavy pages are deferred", () => {
    const wrapper = mountWithPlugins(AlbumViewer, {
      props: {
        album: makeAlbum(),
        media: [],
        steps: [makeStep()],
        segmentOutlines: [],
      },
    });

    expect(wrapper.get('[data-index="0"]').attributes("style")).toContain(
      "min-height: 2365px",
    );
  });

  test("renders virtualized editor maps without a second scroll-window gate", async () => {
    virtualItems.value = [
      {
        key: "chapter-chapter-1-full-map",
        index: 0,
        start: 100_000,
        size: 2365,
        end: 102_365,
      },
    ];

    const wrapper = mountWithPlugins(AlbumViewer, {
      props: {
        album: makeAlbum(),
        media: [],
        steps: [makeStep({ location: { lat: 10, lon: 20 } })],
        segmentOutlines: [
          {
            start_time: 0,
            end_time: 1,
            kind: "driving",
            timezone_id: "UTC",
            start_coord: [10, 20],
            end_coord: [11, 21],
          },
        ],
      },
      global: {
        stubs: {
          MapPage: { template: '<div class="map-page" />' },
        },
      },
    });

    await flushPromises();
    expect(wrapper.find(".map-page").exists()).toBe(true);
  });

  test("keeps hike map boundary editing in virtualized editor pages", () => {
    virtualItems.value = [
      {
        key: "hike-test",
        index: 0,
        start: 0,
        size: 2365,
        end: 2365,
      },
    ];

    const hikeSegment = {
      start_time: 1704067100,
      end_time: 1704067300,
      kind: "hike" as const,
      timezone_id: "UTC",
      start_coord: [10, 20] as [number, number],
      end_coord: [11, 21] as [number, number],
    };
    const wrapper = mountWithPlugins(AlbumViewer, {
      props: {
        album: {
          ...makeAlbum(),
          hidden_headers: ["cover-front", "cover-back", "overview", "full-map"],
          maps_ranges: [["2024-01-01", "2024-01-01"]],
        },
        media: [],
        steps: [
          makeStep({
            timestamp: 1704067200,
            datetime: "2024-01-01T00:00:00Z",
            location: {
              lat: 10,
              lon: 20,
              name: "Trail",
              detail: "",
              country_code: "US",
            },
          }),
        ],
        segmentOutlines: [hikeSegment],
      },
      global: {
        stubs: {
          HikeMapPage: { template: '<div class="hike-map" />' },
          MapPage: { template: '<div class="map-page" />' },
        },
      },
    });

    expect(wrapper.find(".hike-map").exists()).toBe(true);
    expect(wrapper.find(".map-page").exists()).toBe(false);
  });
});
