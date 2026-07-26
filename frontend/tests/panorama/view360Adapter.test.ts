import { beforeEach, describe, expect, it, vi } from "vitest";

const view360Fake = vi.hoisted(() => {
  const projections: Array<{ src: string; partial?: boolean }> = [];
  const viewers: FakeViewer[] = [];

  class FakeProjection {
    constructor(options: { src: string; partial?: boolean }) {
      projections.push(options);
    }
  }

  class FakeViewer {
    camera = {
      lookAt: vi.fn(),
    };
    control = {
      sync: vi.fn(),
    };
    destroy = vi.fn();
    init = vi.fn().mockResolvedValue(undefined);
    renderFrame = vi.fn();
    resize = vi.fn();
    fov: number;
    handlers = new Map<string, (event: unknown) => void>();

    constructor(
      public root: HTMLElement,
      public options: Record<string, unknown>,
    ) {
      this.fov = options.fov as number;
      viewers.push(this);
    }

    on(event: string, handler: (event: unknown) => void) {
      this.handlers.set(event, handler);
    }

    emit(event: string, payload: unknown) {
      this.handlers.get(event)?.(payload);
    }
  }

  return { FakeProjection, FakeViewer, projections, viewers };
});

vi.mock("@egjs/view360", () => ({
  default: view360Fake.FakeViewer,
  CylindricalProjection: view360Fake.FakeProjection,
  EVENTS: { VIEW_CHANGE: "viewChange" },
}));

import { createPanoramaViewerAdapter } from "@/panorama/view360Adapter";

describe("View360 panorama adapter", () => {
  beforeEach(() => {
    view360Fake.projections.length = 0;
    view360Fake.viewers.length = 0;
  });

  it("loads a bounded partial cylinder with library zoom disabled", async () => {
    const root = document.createElement("div");
    const onChange = vi.fn();
    const adapter = createPanoramaViewerAdapter(root);

    await adapter.load({
      src: "/api/v1/albums/a1/media/pano.jpg/panorama-source",
      frame: {
        yaw: 12,
        pitch: -3,
        perspectiveFov: 60,
        zoom: 1.4,
      },
      bounds: {
        yaw: { min: -60, max: 60 },
        pitch: { min: -20, max: 20 },
      },
      onChange,
    });

    expect(view360Fake.projections).toEqual([
      {
        src: "/api/v1/albums/a1/media/pano.jpg/panorama-source",
        partial: true,
      },
    ]);
    expect(root.querySelector("canvas.view360-canvas")).not.toBeNull();
    expect(view360Fake.viewers[0]?.options).toMatchObject({
      autoInit: false,
      autoResize: false,
      fov: 60,
      gyro: false,
      initialPitch: -3,
      initialYaw: 12,
      initialZoom: 1,
      pitchRange: { min: -20, max: 20 },
      scrollable: false,
      useResizeObserver: false,
      yawRange: { min: -60, max: 60 },
      zoom: false,
    });
    expect(view360Fake.viewers[0]?.init).toHaveBeenCalledOnce();
  });

  it("converts camera events to bounded Wanderbound frame drafts", async () => {
    const root = document.createElement("div");
    const onChange = vi.fn();
    const adapter = createPanoramaViewerAdapter(root);

    await adapter.load({
      src: "/panorama.jpg",
      frame: {
        yaw: 0,
        pitch: 0,
        perspectiveFov: 70,
        zoom: 1.8,
        capturedFov: 190,
      },
      bounds: {
        yaw: { min: -50, max: 50 },
        pitch: { min: -15, max: 15 },
      },
      onChange,
    });

    const viewer = view360Fake.viewers[0];
    viewer?.emit("viewChange", { yaw: 80, pitch: -30 });

    expect(viewer?.camera.lookAt).toHaveBeenLastCalledWith({
      yaw: 50,
      pitch: -15,
      zoom: 1,
    });
    expect(onChange).toHaveBeenLastCalledWith({
      yaw: 50,
      pitch: -15,
      perspectiveFov: 70,
      zoom: 1.8,
      capturedFov: 190,
    });
  });

  it("maps Perspective to camera FOV and releases the viewer", async () => {
    const root = document.createElement("div");
    const adapter = createPanoramaViewerAdapter(root);
    const frame = {
      yaw: 8,
      pitch: 4,
      perspectiveFov: 75,
      zoom: 1.2,
    };
    const bounds = {
      yaw: { min: -40, max: 40 },
      pitch: { min: -18, max: 18 },
    };

    await adapter.load({
      src: "/panorama.jpg",
      frame,
      bounds,
      onChange: vi.fn(),
    });
    const viewer = view360Fake.viewers[0];

    adapter.setPerspective(48, bounds);
    expect(viewer?.fov).toBe(48);
    adapter.lookAt({ ...frame, perspectiveFov: 48, zoom: 2 }, bounds);
    adapter.resize();
    adapter.reset(frame, bounds);
    adapter.destroy();

    expect(viewer?.fov).toBe(75);
    expect(viewer?.camera.lookAt).toHaveBeenLastCalledWith({
      yaw: 8,
      pitch: 4,
      zoom: 1,
    });
    expect(viewer?.resize).toHaveBeenCalledOnce();
    expect(viewer?.destroy).toHaveBeenCalledOnce();
    expect(root.querySelector("canvas")).toBeNull();
  });
});
