import { defineComponent } from "vue";
import type { PropType } from "vue";
import { makeAlbumMedia, mountWithPlugins } from "../helpers";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { defaultAlbum, defaultSteps } from "../mocks/handlers";

const mutate = vi.fn();

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate }),
}));

const CoverCellStub = defineComponent({
  name: "CoverCell",
  props: {
    src: { type: String, required: true },
    selected: { type: Boolean, required: true },
    label: { type: String, required: true },
    lazyRoot: { type: Object, default: null },
  },
  template: '<img class="cover-cell" :src="src" alt="" />',
});

const ExpansionItemStub = defineComponent({
  name: "QExpansionItem",
  props: {
    group: { type: String, default: undefined },
    label: { type: String, default: "" },
  },
  template:
    '<section class="expansion-stub" :data-group="group" :data-label="label"><slot /></section>',
});

const VirtualScrollStub = defineComponent({
  name: "QVirtualScroll",
  props: {
    items: {
      type: Array as PropType<unknown[]>,
      required: true,
    },
    virtualScrollSliceSize: {
      type: Number,
      default: 10,
    },
  },
  template:
    '<div class="virtual-scroll-stub"><template v-for="(item, index) in items.slice(0, virtualScrollSliceSize)" :key="index"><slot :item="item" :index="index" /></template></div>',
});

const SliderStub = defineComponent({
  name: "QSlider",
  props: {
    modelValue: { type: Number, required: true },
  },
  emits: ["change", "update:modelValue"],
  template: '<input class="slider-stub" type="range" :value="modelValue" />',
});

function mountCoverInspector(sectionKey: string) {
  return mountWithPlugins(InspectorDrawer, {
    props: {
      album: defaultAlbum,
      sectionKey,
      steps: defaultSteps,
      media: [
        makeAlbumMedia({
          name: "cover.jpg",
          aid: defaultAlbum.id,
        }),
      ],
    },
    global: {
      stubs: {
        AlbumProperties: true,
        CoverCell: CoverCellStub,
        MediaPanel: true,
        QSlider: SliderStub,
        QVirtualScroll: VirtualScrollStub,
        QExpansionItem: ExpansionItemStub,
        QIcon: true,
        QSeparator: true,
        UnusedDrawer: true,
      },
    },
  });
}

describe("InspectorDrawer", () => {
  beforeEach(() => {
    mutate.mockReset();
  });

  it("keeps only properties and external media in the primary accordion", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "step-1",
        step: { ...defaultSteps[0], unused: ["unused.jpg"] },
        steps: defaultSteps,
        media: [
          makeAlbumMedia({
            name: "unused.jpg",
            aid: defaultAlbum.id,
          }),
        ],
      },
      global: {
        stubs: {
          AlbumProperties: true,
          CoverCell: CoverCellStub,
          MediaPanel: true,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QSeparator: true,
          UnusedDrawer: { template: '<div class="unused-drawer-stub" />' },
        },
      },
    });

    const primary = wrapper.findAll(
      '.expansion-stub[data-group="inspector-primary"]',
    );
    expect(primary).toHaveLength(2);
    expect(
      wrapper.find(".inspector-context-tray .unused-drawer-stub").exists(),
    ).toBe(true);
  });

  it("cache-busts cover picker thumbnails with media update time", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "chapter-chapter-1-cover-front",
        steps: defaultSteps,
        media: [
          makeAlbumMedia({
            name: "cover.jpg",
            aid: defaultAlbum.id,
          }),
        ],
      },
      global: {
        stubs: {
          AlbumProperties: true,
          CoverCell: CoverCellStub,
          MediaPanel: true,
          QVirtualScroll: VirtualScrollStub,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QSeparator: true,
          UnusedDrawer: true,
        },
      },
    });

    const url = new URL(wrapper.get(".cover-cell").attributes("src"));
    expect(url.pathname).toBe("/api/v1/albums/aid-1/media/cover.jpg");
    expect(url.searchParams.get("d")).toBe("2026-05-13T12:34:56Z");
  });

  it("excludes panoramas from the cover picker", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "chapter-chapter-1-cover-front",
        steps: defaultSteps,
        media: [
          makeAlbumMedia({ name: "landscape.jpg", aid: defaultAlbum.id }),
          makeAlbumMedia({
            name: "panorama.jpg",
            aid: defaultAlbum.id,
            width: 3000,
            height: 900,
            panorama_candidate: true,
          }),
        ],
      },
      global: {
        stubs: {
          AlbumProperties: true,
          CoverCell: CoverCellStub,
          MediaPanel: true,
          QVirtualScroll: VirtualScrollStub,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QSeparator: true,
          UnusedDrawer: true,
        },
      },
    });

    expect(wrapper.findAll(".cover-cell")).toHaveLength(1);
    expect(wrapper.get(".cover-cell").attributes("src")).toContain(
      "landscape.jpg",
    );
  });

  it("virtualizes the cover picker for large albums", () => {
    const media = Array.from({ length: 100 }, (_, index) =>
      makeAlbumMedia({
        name: `cover-${index}.jpg`,
        aid: defaultAlbum.id,
      }),
    );

    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "chapter-chapter-1-cover-front",
        steps: defaultSteps,
        media,
      },
      global: {
        stubs: {
          AlbumProperties: true,
          CoverCell: CoverCellStub,
          MediaPanel: true,
          QVirtualScroll: VirtualScrollStub,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QSeparator: true,
          UnusedDrawer: true,
        },
      },
    });

    expect(wrapper.findAll(".cover-cell").length).toBeLessThan(media.length);
  });

  it("updates the active chapter darkness from the front cover", async () => {
    const wrapper = mountCoverInspector("chapter-chapter-1-cover-front");

    expect(wrapper.get(".cover-darkness-value").text()).toBe("45%");

    wrapper.getComponent(SliderStub).vm.$emit("update:modelValue", 20);
    await wrapper.vm.$nextTick();

    expect(wrapper.get(".cover-darkness-value").text()).toBe("20%");
    expect(mutate).not.toHaveBeenCalled();

    wrapper.getComponent(SliderStub).vm.$emit("change", 20);
    await wrapper.vm.$nextTick();

    expect(mutate).toHaveBeenCalledOnce();
    expect(mutate.mock.calls[0][0].chapters).toEqual([
      {
        ...defaultAlbum.chapters[0],
        front_cover_darkness: 0.2,
      },
    ]);
  });

  it("does not show chapter darkness for the back cover", () => {
    const wrapper = mountCoverInspector("chapter-chapter-1-cover-back");

    expect(wrapper.find(".cover-darkness-control").exists()).toBe(false);
  });
});
