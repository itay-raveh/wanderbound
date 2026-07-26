import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
import PanoramaSpreadPage from "@/components/album/PanoramaSpreadPage.vue";
import { providePrintMode } from "@/composables/usePrintReady";
import { makeAlbumMedia, provideTestAlbum } from "../helpers";

function mountSpread(printMode = false) {
  const Parent = defineComponent({
    setup() {
      provideTestAlbum({
        media: [
          makeAlbumMedia({
            name: "wide.jpg",
            panorama: {
              status: "active",
              detection: "dimensions",
              source_width: 4000,
              source_height: 1000,
              captured_fov: 180,
              revision: 7,
            },
          }),
        ],
      });
      if (printMode) providePrintMode();
      return () =>
        h(PanoramaSpreadPage, { media: "wide.jpg", side: "left" });
    },
  });
  return mount(Parent);
}

describe("PanoramaSpreadPage", () => {
  test("requests an editor projection matching the full spread ratio", () => {
    const src = new URL(mountSpread().get("img").attributes("src"));

    expect(src.searchParams.get("panorama_revision")).toBe("7");
    expect(
      Number(src.searchParams.get("w")) / Number(src.searchParams.get("h")),
    ).toBeCloseTo((297 * 2) / 210, 2);
  });

  test("requests the high-resolution projection for print", () => {
    const editorSrc = new URL(mountSpread().get("img").attributes("src"));
    const printSrc = new URL(mountSpread(true).get("img").attributes("src"));

    expect(Number(printSrc.searchParams.get("w"))).toBeGreaterThan(
      Number(editorSrc.searchParams.get("w")),
    );
  });
});
