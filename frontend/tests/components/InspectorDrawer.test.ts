import { defineComponent } from "vue";
import { makeAlbumMedia, mountWithPlugins } from "../helpers";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { defaultAlbum, defaultSteps } from "../mocks/handlers";

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

describe("InspectorDrawer", () => {
  it("keeps only properties and external media in the primary accordion", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "step-1",
        step: { ...defaultSteps[0], unused: ["unused.jpg"] },
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
        sectionKey: "cover-front",
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
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QSeparator: true,
          UnusedDrawer: true,
        },
      },
    });

    expect(wrapper.get(".cover-cell").attributes("src")).toBe(
      "http://localhost:8000/api/v1/albums/aid-1/media/cover.jpg?w=200&d=2026-05-13T12%3A34%3A56Z",
    );
  });
});
