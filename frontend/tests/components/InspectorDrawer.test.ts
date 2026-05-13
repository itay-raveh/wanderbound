import { defineComponent } from "vue";
import { mountWithPlugins } from "../helpers";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { defaultAlbum } from "../mocks/handlers";

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

describe("InspectorDrawer", () => {
  it("cache-busts cover picker thumbnails with media update time", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum,
        sectionKey: "cover-front",
        media: [
          {
            uid: 1,
            aid: defaultAlbum.id,
            name: "cover.jpg",
            kind: "photo",
            width: 1920,
            height: 1080,
            byte_size: 1234,
            upgrade_candidate: false,
            created_at: "2026-05-13T12:00:00Z",
            updated_at: "2026-05-13T12:34:56Z",
          },
        ],
      },
      global: {
        stubs: {
          AlbumProperties: true,
          CoverCell: CoverCellStub,
          MediaPanel: true,
          QExpansionItem: { template: "<div><slot /></div>" },
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
