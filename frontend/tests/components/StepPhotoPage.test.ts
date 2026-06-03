import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import StepPhotoPage from "@/components/album/step/StepPhotoPage.vue";
import { provideTestAlbum } from "../helpers";

const visible = ref(false);
const start = vi.fn();
const destroy = vi.fn();

vi.mock("@vueuse/core", () => ({
  useElementVisibility: () => visible,
}));

vi.mock("vue-draggable-plus", () => ({
  useDraggable: vi.fn(() => ({
    start,
    destroy,
    pause: vi.fn(),
    resume: vi.fn(),
  })),
}));

describe("StepPhotoPage", () => {
  beforeEach(() => {
    visible.value = false;
    start.mockClear();
    destroy.mockClear();
  });

  test("starts drag handling only while the photo page is near the viewport", async () => {
    const Parent = defineComponent({
      setup() {
        provideTestAlbum();
        return () => h(StepPhotoPage, { page: ["one.jpg", "two.jpg"] });
      },
    });

    mount(Parent, {
      global: {
        stubs: {
          MediaItem: { template: "<div />" },
        },
      },
    });

    expect(start).not.toHaveBeenCalled();

    visible.value = true;
    await Promise.resolve();

    expect(start).toHaveBeenCalledTimes(1);

    visible.value = false;
    await Promise.resolve();

    expect(destroy).toHaveBeenCalledTimes(1);
  });
});
