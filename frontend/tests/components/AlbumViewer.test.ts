import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ref, type Ref } from "vue";
import AlbumViewer from "@/components/AlbumViewer.vue";
import { mountWithPlugins, makeStep } from "../helpers";
import type { AlbumMeta } from "@/client";

type TestVirtualItem = {
  key: string;
  index: number;
  start: number;
  size: number;
  end: number;
};

let virtualItems: Ref<TestVirtualItem[]>;

vi.mock("@/composables/useWindowVirtualizer", () => ({
  useWindowVirtualizer: () => ({
    virtualizer: {
      scrollToIndex: vi.fn(),
    },
    items: virtualItems,
    size: ref(2365),
    version: ref(0),
  }),
}));

function makeAlbum(): AlbumMeta {
  return {
    uid: 1,
    id: "album-1",
    title: "Album",
    subtitle: "",
    hidden_headers: ["cover-front", "cover-back", "overview"],
    hidden_steps: [],
    maps_ranges: [],
    front_cover_photo: "",
    back_cover_photo: "",
    colors: {},
  };
}

beforeEach(() => {
  virtualItems = ref([
    {
      key: "full-map",
      index: 0,
      start: 0,
      size: 2365,
      end: 2365,
    },
  ]);
});

describe("AlbumViewer", () => {
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
        key: "full-map",
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
          StaticMapPreview: { template: '<div class="static-map" />' },
        },
      },
    });

    await flushPromises();
    expect(wrapper.find(".static-map").exists()).toBe(true);
  });
});
