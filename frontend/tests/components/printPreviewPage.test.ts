import { mount } from "@vue/test-utils";
import { defineComponent, h, nextTick, onMounted } from "vue";
import { createI18n } from "vue-i18n";
import PrintPreviewPage from "@/components/editor/PrintPreviewPage.vue";
import { usePrintMapState } from "@/composables/usePrintReady";
import type { AlbumMeta } from "@/client";

vi.mock("@/components/album/PhysicalAlbumPage.vue", () => ({
  default: defineComponent({
    setup() {
      const state = usePrintMapState();
      onMounted(() => {
        state!.value = "error";
      });
      return () => h("div");
    },
  }),
}));

test("surfaces synchronous map initialization failure on first mount", async () => {
  const wrapper = mount(PrintPreviewPage, {
    props: {
      item: {
        type: "header",
        headerKey: "full-map",
        key: "map",
        chapter: {
          id: "chapter-1",
          title: "Chapter",
          subtitle: "",
          front_cover_photo: "",
          back_cover_photo: "",
        },
        steps: [],
        segments: [],
      },
      album: {} as AlbumMeta,
      segmentOutlines: [],
      width: 1000,
      height: 700,
      scale: 1,
    },
    global: {
      plugins: [
        createI18n({
          legacy: false,
          locale: "en",
          messages: {
            en: {
              print: {
                mapLoading: "Loading",
                mapFailed: "Failed",
                retryMap: "Retry",
              },
            },
          },
        }),
      ],
      mocks: { $q: { lang: { rtl: false } } },
      stubs: {
        QBtn: { template: "<button>{{ label }}</button>", props: ["label"] },
      },
    },
  });
  await nextTick();
  expect(wrapper.get('[role="status"]').text()).toBe("Failed");
  expect(wrapper.get("button").text()).toBe("Retry");
  wrapper.unmount();
});
