import { defineComponent } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AlbumMedia, PanoramaDestination } from "@/client";
import i18n from "@/i18n";
import { deferred, makeAlbumMedia } from "../helpers";

const adapterFake = vi.hoisted(() => {
  const adapter = {
    destroy: vi.fn(),
    cancelInteraction: vi.fn(),
    load: vi.fn().mockResolvedValue(undefined),
    lookAt: vi.fn(),
    reset: vi.fn(),
    resize: vi.fn(),
    setPerspective: vi.fn(),
  };
  return {
    adapter,
    create: vi.fn(() => adapter),
  };
});

const panoramaMutation = vi.hoisted(() => ({ mutateAsync: vi.fn() }));

vi.mock("@/panorama/view360Adapter", () => ({
  createPanoramaViewerAdapter: adapterFake.create,
}));

vi.mock("@/queries/usePanoramaMutation", () => ({
  usePanoramaMutation: () => panoramaMutation,
}));

import PanoramaFrameDialog from "@/components/editor/PanoramaFrameDialog.vue";

const QDialogStub = defineComponent({
  props: { modelValue: Boolean },
  template: '<div v-if="modelValue"><slot /></div>',
});

const QBtnStub = defineComponent({
  inheritAttrs: false,
  props: {
    disable: Boolean,
    label: String,
    loading: Boolean,
  },
  emits: ["click"],
  template:
    '<button v-bind="$attrs" :disabled="disable || loading" @click="$emit(\'click\')">{{ label }}</button>',
});

const passthrough = defineComponent({ template: "<div><slot /></div>" });

function panoramaMedia(detection: "gpano" | "dimensions" = "gpano") {
  return makeAlbumMedia({
    name: "wide view.jpg",
    panorama: {
      status: "active",
      detection,
      source_width: 1600,
      source_height: 800,
      captured_fov: 180,
      yaw: 0,
      pitch: 0,
      perspective_fov: 60,
      zoom: 1.5,
      revision: 3,
    },
  });
}

const destination: PanoramaDestination = {
  kind: "panorama_spread",
  aspect_ratio: 2,
  width_px: 1600,
  height_px: 800,
};

function mountDialog(
  overrides: Partial<{
    modelValue: boolean;
    media: AlbumMedia;
    destination: PanoramaDestination;
  }> = {},
) {
  return mount(PanoramaFrameDialog, {
    props: {
      modelValue: false,
      albumId: "a1",
      media: panoramaMedia(),
      destination,
      ...overrides,
    },
    global: {
      plugins: [i18n],
      stubs: {
        QDialog: QDialogStub,
        QCard: passthrough,
        QCardSection: passthrough,
        QCardActions: passthrough,
        QBtn: QBtnStub,
      },
    },
  });
}

describe("PanoramaFrameDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adapterFake.adapter.load.mockResolvedValue(undefined);
  });

  it("lazy-loads the saved frame and shows a destination-shaped spread seam", async () => {
    const media = panoramaMedia();
    media.panorama!.yaw = -12;
    media.panorama!.pitch = -4;
    const wrapper = mountDialog({ media });

    expect(adapterFake.create).not.toHaveBeenCalled();

    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    expect(adapterFake.create).toHaveBeenCalledOnce();
    expect(adapterFake.adapter.load).toHaveBeenCalledWith(
      expect.objectContaining({
        src: "/api/v1/albums/a1/media/wide%20view.jpg/panorama-source",
        frame: expect.objectContaining({
          yaw: -12,
          pitch: -4,
          perspectiveFov: 60,
          zoom: 1.5,
        }),
        accessibleLabel: "Interactive panorama preview",
      }),
    );
    expect(wrapper.get(".panorama-viewport").attributes("style")).toContain(
      "aspect-ratio: 2",
    );
    expect(wrapper.find(".spread-seam").exists()).toBe(true);
    expect(wrapper.text()).toContain("60°");
    expect(wrapper.text()).toContain("1.5×");
  });

  it("keeps Perspective separate from ordinary wheel and pinch Zoom", async () => {
    const wrapper = mountDialog({ modelValue: true });
    await flushPromises();
    const viewport = wrapper.get(".panorama-viewport");

    await viewport.trigger("wheel", { deltaY: -100 });

    expect(wrapper.text()).toContain("1.6×");
    expect(adapterFake.adapter.setPerspective).not.toHaveBeenCalled();
    expect(wrapper.get(".panorama-projection-layer").attributes("style")).toContain(
      "--panorama-zoom: 1.6",
    );

    const perspective = wrapper.get<HTMLInputElement>(
      'input[name="perspective"]',
    );
    await perspective.setValue("80");

    expect(adapterFake.adapter.setPerspective).toHaveBeenCalledWith(
      80,
      expect.any(Object),
    );
    expect(wrapper.text()).toContain("80°");

    await viewport.trigger("touchstart", {
      touches: [
        { clientX: 0, clientY: 0 },
        { clientX: 100, clientY: 0 },
      ],
    });
    await viewport.trigger("touchmove", {
      touches: [
        { clientX: 0, clientY: 0 },
        { clientX: 150, clientY: 0 },
      ],
    });

    expect(wrapper.text()).toContain("2.4×");
    expect(adapterFake.adapter.setPerspective).toHaveBeenCalledTimes(1);
    expect(adapterFake.adapter.cancelInteraction).toHaveBeenCalledOnce();
  });

  it("resets to auto-fit, rolls transient changes back on Cancel, and cleans up", async () => {
    const wrapper = mountDialog({ modelValue: true });
    await flushPromises();
    const zoom = wrapper.get<HTMLInputElement>('input[name="zoom"]');

    await zoom.setValue("2.5");
    await wrapper.get('input[name="perspective"]').setValue("70");
    await wrapper.get(".reset-button").trigger("click");

    expect(wrapper.text()).toContain("115°");
    expect(wrapper.text()).toContain("1.0×");
    expect(adapterFake.adapter.reset).toHaveBeenCalledWith(
      expect.objectContaining({
        perspectiveFov: 115.0367268189405,
        zoom: 1,
      }),
      expect.any(Object),
    );

    await zoom.setValue("2");
    await wrapper.get(".cancel-button").trigger("click");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);

    await wrapper.setProps({ modelValue: false });
    expect(adapterFake.adapter.destroy).toHaveBeenCalledOnce();

    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(wrapper.text()).toContain("1.5×");

    wrapper.unmount();
    expect(adapterFake.adapter.destroy).toHaveBeenCalledTimes(2);
  });

  it("shows Captured width only for metadata-free panoramas", async () => {
    const gpano = mountDialog({ modelValue: true });
    await flushPromises();
    expect(gpano.find('input[name="captured-width"]').exists()).toBe(false);
    gpano.unmount();
    vi.clearAllMocks();

    const estimated = mountDialog({
      modelValue: true,
      media: panoramaMedia("dimensions"),
    });
    await flushPromises();
    const capturedWidth = estimated.get<HTMLInputElement>(
      'input[name="captured-width"]',
    );
    expect(capturedWidth.exists()).toBe(true);

    await capturedWidth.setValue("240");
    await flushPromises();

    expect(adapterFake.adapter.destroy).toHaveBeenCalledOnce();
    expect(adapterFake.adapter.load).toHaveBeenLastCalledWith(
      expect.objectContaining({
        src: "/api/v1/albums/a1/media/wide%20view.jpg/panorama-source?captured_fov=240",
        frame: expect.objectContaining({ capturedFov: 240 }),
      }),
    );
  });

  it("normalizes metadata-free captured width to the integer API precision", async () => {
    const media = panoramaMedia("dimensions");
    media.panorama!.captured_fov = 180.4;
    mountDialog({ modelValue: true, media });

    await flushPromises();

    expect(adapterFake.adapter.load).toHaveBeenCalledWith(
      expect.objectContaining({
        src: "/api/v1/albums/a1/media/wide%20view.jpg/panorama-source?captured_fov=180",
        frame: expect.objectContaining({ capturedFov: 180 }),
      }),
    );
  });

  it("owns pinch until every touch ends", async () => {
    const wrapper = mountDialog({ modelValue: true });
    await flushPromises();
    const viewport = wrapper.get(".panorama-viewport").element;
    const bubbled = vi.fn();
    wrapper.element.addEventListener("touchend", bubbled);
    const touchEvent = (type: string, touches: Array<{ clientX: number; clientY: number }>) => {
      const event = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(event, "touches", { value: touches });
      return event;
    };

    viewport.dispatchEvent(
      touchEvent("touchstart", [
        { clientX: 0, clientY: 0 },
        { clientX: 100, clientY: 0 },
      ]),
    );
    const oneFingerEnd = touchEvent("touchend", [{ clientX: 0, clientY: 0 }]);
    viewport.dispatchEvent(oneFingerEnd);
    const finalEnd = touchEvent("touchend", []);
    viewport.dispatchEvent(finalEnd);

    expect(oneFingerEnd.defaultPrevented).toBe(true);
    expect(finalEnd.defaultPrevented).toBe(true);
    expect(bubbled).not.toHaveBeenCalled();
    expect(adapterFake.adapter.cancelInteraction).toHaveBeenCalledOnce();
  });

  it("connects dialog labels and announces loading failures", async () => {
    let rejectLoad!: (reason: unknown) => void;
    const loading = new Promise<void>((_resolve, reject) => {
      rejectLoad = reject;
    });
    adapterFake.adapter.load.mockReturnValueOnce(loading);
    const wrapper = mountDialog({ modelValue: true });
    await Promise.resolve();

    expect(wrapper.attributes("aria-labelledby")).toBe("panorama-frame-title");
    expect(wrapper.attributes("aria-describedby")).toBe(
      "panorama-frame-description",
    );
    expect(wrapper.get(".viewport-status").attributes()).toMatchObject({
      role: "status",
      "aria-live": "polite",
    });

    rejectLoad(new Error("WebGL unavailable"));
    await flushPromises();

    expect(wrapper.get(".viewport-error").attributes("role")).toBe("alert");
  });

  it("emits applied only after the backend returns the committed media row", async () => {
    const pending = deferred<AlbumMedia>();
    const committed = panoramaMedia();
    committed.panorama!.revision = 4;
    panoramaMutation.mutateAsync.mockReturnValueOnce(pending.promise);
    const wrapper = mountDialog({ modelValue: true });
    await flushPromises();

    await wrapper.get(".apply-button").trigger("click");

    expect(panoramaMutation.mutateAsync).toHaveBeenCalledWith({
      aid: "a1",
      name: "wide view.jpg",
      frame: {
        yaw: 0,
        pitch: 0,
        perspective_fov: 60,
        zoom: 1.5,
      },
      destination,
    });
    expect(wrapper.emitted("applied")).toBeUndefined();
    expect(wrapper.get(".apply-button").attributes()).toHaveProperty("disabled");

    pending.resolve(committed);
    await flushPromises();

    expect(wrapper.emitted("applied")).toEqual([[committed]]);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });
});
