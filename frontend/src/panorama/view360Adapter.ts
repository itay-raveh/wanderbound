import "@egjs/view360/css/base.css";
import View360, {
  CylindricalProjection,
  EVENTS,
  type ViewChangeEvent,
} from "@egjs/view360";
import type {
  PanoramaCameraBounds,
  PanoramaFrameDraft,
} from "./frame";

interface PanoramaViewerLoadOptions {
  src: string;
  frame: PanoramaFrameDraft;
  bounds: PanoramaCameraBounds;
  onChange: (frame: PanoramaFrameDraft) => void;
}

export interface PanoramaViewerAdapter {
  load(options: PanoramaViewerLoadOptions): Promise<void>;
  lookAt(frame: PanoramaFrameDraft, bounds: PanoramaCameraBounds): void;
  setPerspective(
    perspectiveFov: number,
    bounds: PanoramaCameraBounds,
  ): void;
  resize(): void;
  reset(frame: PanoramaFrameDraft, bounds: PanoramaCameraBounds): void;
  destroy(): void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function createPanoramaViewerAdapter(
  root: HTMLElement,
): PanoramaViewerAdapter {
  let viewer: View360 | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let frame: PanoramaFrameDraft | null = null;
  let bounds: PanoramaCameraBounds | null = null;
  let onChange: ((next: PanoramaFrameDraft) => void) | null = null;

  function boundedFrame(next: PanoramaFrameDraft): PanoramaFrameDraft {
    if (!bounds) return next;
    return {
      ...next,
      yaw: clamp(next.yaw, bounds.yaw.min, bounds.yaw.max),
      pitch: clamp(next.pitch, bounds.pitch.min, bounds.pitch.max),
    };
  }

  function applyLookAt(next: PanoramaFrameDraft, emit: boolean): void {
    if (!viewer) return;
    frame = boundedFrame(next);
    viewer.camera.lookAt({ yaw: frame.yaw, pitch: frame.pitch, zoom: 1 });
    viewer.control.sync();
    viewer.renderFrame(0);
    if (emit) onChange?.({ ...frame });
  }

  function handleViewChange(event: ViewChangeEvent): void {
    if (!frame || !viewer) return;
    const next = boundedFrame({ ...frame, yaw: event.yaw, pitch: event.pitch });
    if (next.yaw !== event.yaw || next.pitch !== event.pitch) {
      viewer.camera.lookAt({ yaw: next.yaw, pitch: next.pitch, zoom: 1 });
      viewer.control.sync();
      viewer.renderFrame(0);
    }
    frame = next;
    onChange?.({ ...next });
  }

  function destroy(): void {
    viewer?.destroy();
    viewer = null;
    canvas?.remove();
    canvas = null;
    frame = null;
    bounds = null;
    onChange = null;
    root.classList.remove("view360-container");
  }

  return {
    async load(options) {
      destroy();
      frame = { ...options.frame };
      bounds = options.bounds;
      onChange = options.onChange;
      root.classList.add("view360-container");
      canvas = document.createElement("canvas");
      canvas.className = "view360-canvas";
      root.append(canvas);

      const projection = new CylindricalProjection({
        src: options.src,
        partial: true,
      });
      viewer = new View360(root, {
        projection,
        autoInit: false,
        autoResize: false,
        useResizeObserver: false,
        initialYaw: frame.yaw,
        initialPitch: frame.pitch,
        initialZoom: 1,
        yawRange: bounds.yaw,
        pitchRange: bounds.pitch,
        fov: frame.perspectiveFov,
        rotate: true,
        zoom: false,
        gyro: false,
        scrollable: false,
        wheelScrollable: false,
      });
      viewer.on(EVENTS.VIEW_CHANGE, handleViewChange);
      await viewer.init();
      applyLookAt(frame, false);
    },
    lookAt(next, nextBounds) {
      bounds = nextBounds;
      applyLookAt(next, true);
    },
    setPerspective(perspectiveFov, nextBounds) {
      if (!viewer || !frame) return;
      bounds = nextBounds;
      frame = { ...frame, perspectiveFov };
      viewer.fov = perspectiveFov;
      applyLookAt(frame, true);
    },
    resize() {
      viewer?.resize();
    },
    reset(next, nextBounds) {
      if (!viewer) return;
      bounds = nextBounds;
      frame = { ...next };
      viewer.fov = frame.perspectiveFov;
      applyLookAt(frame, true);
    },
    destroy,
  };
}
