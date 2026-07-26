import "@egjs/view360/css/base.css";
import View360, {
  EquirectProjection,
  EVENTS,
  type ViewChangeEvent,
} from "@egjs/view360";
import type { PanoramaCameraBounds, PanoramaFrameDraft } from "./frame";

interface PanoramaViewerLoadOptions {
  src: string;
  frame: PanoramaFrameDraft;
  bounds: PanoramaCameraBounds;
  onChange: (frame: PanoramaFrameDraft) => void;
}

export interface PanoramaViewerAdapter {
  load(options: PanoramaViewerLoadOptions): Promise<void>;
  update(frame: PanoramaFrameDraft, bounds: PanoramaCameraBounds): void;
  resize(): void;
  destroy(): void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function signedYaw(value: number): number {
  return ((((value + 180) % 360) + 360) % 360) - 180;
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
      yaw: clamp(signedYaw(next.yaw), bounds.yaw.min, bounds.yaw.max),
      pitch: clamp(next.pitch, bounds.pitch.min, bounds.pitch.max),
    };
  }

  function enforceCameraState(target: PanoramaFrameDraft): void {
    if (!viewer) return;
    viewer.camera.restrictZoomRange(1, 1);
    viewer.camera.lookAt({ yaw: target.yaw, pitch: target.pitch, zoom: 1 });
    // lookAt circulates negative yaw before beta.7 sync clamps signed ranges.
    // https://github.com/naver/egjs-view360/issues/454
    viewer.camera.yaw = target.yaw;
    viewer.control.sync();
  }

  function applyLookAt(next: PanoramaFrameDraft, emit: boolean): void {
    if (!viewer) return;
    frame = boundedFrame(next);
    enforceCameraState(frame);
    viewer.renderFrame(0);
    if (emit) onChange?.({ ...frame });
  }

  function handleViewChange(event: ViewChangeEvent): void {
    if (!frame || !viewer) return;
    const eventYaw = signedYaw(event.yaw);
    const next = boundedFrame({ ...frame, yaw: eventYaw, pitch: event.pitch });
    if (
      next.yaw !== eventYaw ||
      next.pitch !== event.pitch ||
      event.zoom !== 1 ||
      viewer.camera.zoom !== 1
    ) {
      enforceCameraState(next);
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

      const projection = new EquirectProjection({
        src: options.src,
      });
      const createdViewer = new View360(root, {
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
      viewer = createdViewer;
      createdViewer.on(EVENTS.VIEW_CHANGE, handleViewChange);
      try {
        await createdViewer.init();
      } catch (error) {
        createdViewer.destroy();
        if (viewer === createdViewer) destroy();
        throw error;
      }
      if (viewer !== createdViewer || !frame) {
        createdViewer.destroy();
        return;
      }
      applyLookAt(frame, false);
    },
    update(next, nextBounds) {
      if (!viewer || !frame) return;
      bounds = nextBounds;
      if (next.perspectiveFov !== frame.perspectiveFov) {
        viewer.fov = next.perspectiveFov;
      }
      applyLookAt(next, true);
    },
    resize() {
      viewer?.resize();
    },
    destroy,
  };
}
