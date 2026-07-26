import { beforeEach, describe, expect, it, vi } from "vitest";
import { deferred } from "../helpers";

const view360Fake = vi.hoisted(() => {
  const projections: Array<{ src: string; partial?: boolean }> = [];
  const viewers: FakeViewer[] = [];
  const state = {
    initPromise: Promise.resolve(),
  };

  class FakeProjection {
    constructor(options: { src: string; partial?: boolean }) {
      projections.push(options);
    }
  }

  class FakeViewer {
    camera: {
      yaw: number;
      pitch: number;
      zoom: number;
      zoomRange: { min: number; max: number };
      lookAt: ReturnType<typeof vi.fn>;
      restrictZoomRange: ReturnType<typeof vi.fn>;
    };
    control: {
      disable: ReturnType<typeof vi.fn>;
      enable: ReturnType<typeof vi.fn>;
      sync: ReturnType<typeof vi.fn>;
      update: ReturnType<typeof vi.fn>;
    };
    destroy = vi.fn();
    init = vi.fn(() => state.initPromise);
    renderFrame: ReturnType<typeof vi.fn>;
    resize = vi.fn();
    private _fov: number;
    handlers = new Map<string, (event: unknown) => void>();

    constructor(
      public root: HTMLElement,
      public options: Record<string, unknown>,
    ) {
      this._fov = options.fov as number;
      this.camera = {
        yaw: options.initialYaw as number,
        pitch: options.initialPitch as number,
        zoom: options.initialZoom as number,
        zoomRange: { min: 1.6, max: Number.POSITIVE_INFINITY },
        lookAt: vi.fn((next: { yaw?: number; pitch?: number; zoom?: number }) => {
          if (next.yaw != null) {
            this.camera.yaw = ((next.yaw % 360) + 360) % 360;
          }
          if (next.pitch != null) this.camera.pitch = next.pitch;
          if (next.zoom != null) this.camera.zoom = next.zoom;
        }),
        restrictZoomRange: vi.fn((min: number, max: number) => {
          this.camera.zoomRange = { min, max };
        }),
      };
      this.control = {
        disable: vi.fn(),
        enable: vi.fn().mockResolvedValue(undefined),
        sync: vi.fn(),
        update: vi.fn(() => {
          this.camera.lookAt({ zoom: this.camera.zoomRange.min });
        }),
      };
      this.renderFrame = vi.fn(() => this.control.update());
      viewers.push(this);
    }

    get fov() {
      return this._fov;
    }

    set fov(value: number) {
      this._fov = value;
      this.control.sync();
    }

    on(event: string, handler: (event: unknown) => void) {
      this.handlers.set(event, handler);
    }

    emit(event: string, payload: unknown) {
      this.handlers.get(event)?.(payload);
    }
  }

  return { FakeProjection, FakeViewer, projections, state, viewers };
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
    view360Fake.state.initPromise = Promise.resolve();
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
      accessibleLabel: "Interactive panorama preview",
      onChange,
    });

    expect(view360Fake.projections).toEqual([
      {
        src: "/api/v1/albums/a1/media/pano.jpg/panorama-source",
        partial: true,
      },
    ]);
    expect(root.querySelector("canvas.view360-canvas")).not.toBeNull();
    expect(root.querySelector("canvas")?.getAttribute("aria-label")).toBe(
      "Interactive panorama preview",
    );
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
    expect(view360Fake.viewers[0]?.camera.zoom).toBe(1);
    expect(
      view360Fake.viewers[0]?.camera.restrictZoomRange,
    ).toHaveBeenLastCalledWith(1, 1);
  });

  it("converts wrapped camera yaw to signed bounded frame drafts", async () => {
    const root = document.createElement("div");
    const onChange = vi.fn();
    const adapter = createPanoramaViewerAdapter(root);

    await adapter.load({
      src: "/panorama.jpg",
      frame: {
        yaw: -25,
        pitch: 0,
        perspectiveFov: 70,
        zoom: 1.8,
        capturedFov: 190,
      },
      bounds: {
        yaw: { min: -50, max: 50 },
        pitch: { min: -15, max: 15 },
      },
      accessibleLabel: "Interactive panorama preview",
      onChange,
    });

    const viewer = view360Fake.viewers[0];
    expect(viewer?.camera.yaw).toBe(335);
    viewer?.emit("viewChange", { yaw: 335, pitch: -30, zoom: 2.4 });

    expect(viewer?.camera.lookAt).toHaveBeenLastCalledWith({
      yaw: -25,
      pitch: -15,
      zoom: 1,
    });
    expect(viewer?.camera.zoom).toBe(1);
    expect(onChange).toHaveBeenLastCalledWith({
      yaw: -25,
      pitch: -15,
      perspectiveFov: 70,
      zoom: 1.8,
      capturedFov: 190,
    });
  });

  it("keeps signed left-drag events without resynchronizing rotation", async () => {
    const root = document.createElement("div");
    const onChange = vi.fn();
    const adapter = createPanoramaViewerAdapter(root);
    await adapter.load({
      src: "/panorama.jpg",
      frame: { yaw: 0, pitch: 0, perspectiveFov: 60, zoom: 1 },
      bounds: {
        yaw: { min: -60, max: 60 },
        pitch: { min: -20, max: 20 },
      },
      accessibleLabel: "Interactive panorama preview",
      onChange,
    });
    const viewer = view360Fake.viewers[0];
    viewer?.camera.lookAt.mockClear();
    viewer?.control.sync.mockClear();

    viewer?.emit("viewChange", { yaw: 350, pitch: 0, zoom: 1 });

    expect(onChange).toHaveBeenLastCalledWith({
      yaw: -10,
      pitch: 0,
      perspectiveFov: 60,
      zoom: 1,
    });
    expect(viewer?.camera.lookAt).not.toHaveBeenCalled();
    expect(viewer?.control.sync).not.toHaveBeenCalled();
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
      accessibleLabel: "Interactive panorama preview",
      onChange: vi.fn(),
    });
    const viewer = view360Fake.viewers[0];

    adapter.setPerspective(48, bounds);
    expect(viewer?.fov).toBe(48);
    expect(viewer?.camera.zoom).toBe(1);
    viewer?.control.update();
    expect(viewer?.camera.zoom).toBe(1);
    adapter.lookAt({ ...frame, perspectiveFov: 48, zoom: 2 }, bounds);
    adapter.resize();
    adapter.reset(frame, bounds);
    adapter.destroy();

    expect(viewer?.fov).toBe(75);
    expect(viewer?.camera.lookAt).toHaveBeenCalledWith({
      yaw: 8,
      pitch: 4,
      zoom: 1,
    });
    expect(viewer?.camera).toMatchObject({ yaw: 8, pitch: 4, zoom: 1 });
    expect(viewer?.resize).toHaveBeenCalledOnce();
    expect(viewer?.destroy).toHaveBeenCalledOnce();
    expect(root.querySelector("canvas")).toBeNull();
  });

  it("destroys an initializing viewer again when its load resumes", async () => {
    const pending = deferred<void>();
    view360Fake.state.initPromise = pending.promise;
    const root = document.createElement("div");
    const adapter = createPanoramaViewerAdapter(root);
    const loading = adapter.load({
      src: "/panorama.jpg",
      frame: { yaw: 0, pitch: 0, perspectiveFov: 60, zoom: 1 },
      bounds: {
        yaw: { min: -60, max: 60 },
        pitch: { min: -20, max: 20 },
      },
      accessibleLabel: "Interactive panorama preview",
      onChange: vi.fn(),
    });
    await Promise.resolve();
    const viewer = view360Fake.viewers[0];

    adapter.destroy();
    expect(viewer?.destroy).toHaveBeenCalledOnce();

    pending.resolve();
    await loading;

    expect(viewer?.destroy).toHaveBeenCalledTimes(2);
    expect(root.querySelector("canvas")).toBeNull();
  });
});
