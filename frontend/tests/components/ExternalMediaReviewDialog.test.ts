import { mountWithPlugins } from "../helpers";
import ExternalMediaReviewDialog from "@/components/editor/ExternalMediaReviewDialog.vue";
import type { ReplacementReviewState } from "@/composables/useReplaceExternalMedia";

function videoReview(): ReplacementReviewState {
  return {
    mediaName: "clip.mp4",
    current: {
      kind: "video",
      width: 1920,
      height: 1080,
      previewUrl: "/media/clip.jpg",
    },
    replacement: {
      file: new File(["video"], "replacement.mp4", { type: "video/mp4" }),
      kind: "video",
      width: 1920,
      height: 1080,
      previewUrl: "blob:replacement",
    },
    warnings: [],
    blockedReason: null,
  };
}

describe("ExternalMediaReviewDialog", () => {
  test("renders current video preview from the poster image", () => {
    const wrapper = mountWithPlugins(ExternalMediaReviewDialog, {
      props: {
        modelValue: true,
        review: videoReview(),
      },
      global: {
        stubs: {
          QDialog: { template: "<div><slot /></div>" },
        },
      },
    });

    const panels = wrapper.findAll(".preview-panel");
    expect(panels[0].get("img").attributes("src")).toBe("/media/clip.jpg");
    expect(panels[0].find("video").exists()).toBe(false);
    expect(panels[1].get("video").attributes("src")).toBe("blob:replacement");
  });
});
