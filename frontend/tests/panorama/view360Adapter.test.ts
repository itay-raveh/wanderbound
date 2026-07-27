import { beforeEach, describe, expect, it, vi } from "vitest";

const view360Fake = vi.hoisted(() => {
  const viewers: FakeViewer[] = [];
  const controlBars: FakeControlBar[] = [];

  class FakeProjection {}

  class FakeControlBar {
    constructor(public options: Record<string, unknown>) {
      controlBars.push(this);
    }
  }

  class FakeViewer {
    camera: {
      yaw: number;
      pitch: number;
      zoom: number;
      lookAt: ReturnType<typeof vi.fn>;
      restrictZoomRange: ReturnType<typeof vi.fn>;
    };
    control = { sync: vi.fn() };
    destroy = vi.fn();
    init = vi.fn().mockResolvedValue(undefined);
    renderFrame = vi.fn(() => {
      this.camera.yaw = ((this.camera.yaw % 360) + 360) % 360;
    });
    resize = vi.fn();
    fov: number;
    options: Record<string, unknown>;
    handlers = new Map<string, (event: unknown) => void>();

    constructor(_root: HTMLElement, options: Record<string, unknown>) {
      this.options = options;
      this.fov = options.fov as number;
      this.camera = {
        yaw: options.initialYaw as number,
        pitch: options.initialPitch as number,
        zoom: options.initialZoom as number,
        lookAt: vi.fn((next: { yaw?: number; pitch?: number; zoom?: number }) => {
          if (next.yaw != null) this.camera.yaw = next.yaw;
          if (next.pitch != null) this.camera.pitch = next.pitch;
          if (next.zoom != null) this.camera.zoom = next.zoom;
        }),
        restrictZoomRange: vi.fn(),
      };
      viewers.push(this);
    }

    on(event: string, handler: (event: unknown) => void) {
      this.handlers.set(event, handler);
    }

    emit(event: string, payload: unknown) {
      this.handlers.get(event)?.(payload);
    }
  }

  return { controlBars, FakeControlBar, FakeProjection, FakeViewer, viewers };
});

vi.mock("@egjs/view360", () => ({
  default: view360Fake.FakeViewer,
  ControlBar: view360Fake.FakeControlBar,
  EquirectProjection: view360Fake.FakeProjection,
  EVENTS: { VIEW_CHANGE: "viewChange" },
}));

import { createPanoramaViewerAdapter } from "@/panorama/view360Adapter";

describe("View360 panorama adapter", () => {
  beforeEach(() => {
    view360Fake.viewers.length = 0;
    view360Fake.controlBars.length = 0;
  });

  it("keeps negative yaw through exact-beta-style control synchronization", async () => {
    const root = document.createElement("div");
    const onChange = vi.fn();
    const adapter = createPanoramaViewerAdapter(root);
    const bounds = {
      yaw: { min: -50, max: 50 },
      pitch: { min: -15, max: 15 },
    };
    const frame = {
      yaw: -25,
      pitch: 0,
      perspectiveFov: 70,
      zoom: 1.8,
    };

    await adapter.load({
      src: "/panorama.jpg",
      frame,
      bounds,
      onChange,
    });
    const viewer = view360Fake.viewers[0];
    expect(viewer?.camera.yaw).toBe(335);

    adapter.update({ ...frame, yaw: -30, zoom: 2 }, bounds);
    expect(viewer?.camera.yaw).toBe(330);

    adapter.update({ ...frame, yaw: -35, perspectiveFov: 55 }, bounds);
    expect(viewer?.camera.yaw).toBe(325);
    expect(viewer?.fov).toBe(55);

    viewer?.emit("viewChange", { yaw: 330, pitch: -30, zoom: 2 });
    viewer?.renderFrame(0);
    expect(viewer?.camera.yaw).toBe(330);
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ yaw: -30, pitch: -15 }),
    );
  });

  it("uses the built-in camera direction control", async () => {
    const adapter = createPanoramaViewerAdapter(document.createElement("div"));

    await adapter.load({
      src: "/panorama.jpg",
      frame: { yaw: 0, pitch: 0, perspectiveFov: 70, zoom: 1 },
      bounds: {
        yaw: { min: -50, max: 50 },
        pitch: { min: -15, max: 15 },
      },
      onChange: vi.fn(),
    });

    expect(view360Fake.controlBars).toHaveLength(1);
    expect(view360Fake.controlBars[0]?.options).toMatchObject({
      pieView: { resetCamera: false },
      playButton: false,
      progressBar: false,
      volumeButton: false,
      videoTime: false,
    });
  });
});
