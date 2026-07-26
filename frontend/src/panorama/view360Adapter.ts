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
  accessibleLabel: string;
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
  cancelInteraction(): void;
  destroy(): void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function signedYaw(value: number): number {
  return ((value + 180) % 360 + 360) % 360 - 180;
}

export function createPanoramaViewerAdapter(
  root: HTMLElement,
): PanoramaViewerAdapter {
  let viewer: View360 | null = null;
  let canvas: HTMLCanvasElement | null = null;
  let frame: PanoramaFrameDraft | null = null;
  let bounds: PanoramaCameraBounds | null = null;
  let onChange: ((next: PanoramaFrameDraft) => void) | null = null;
  let loadGeneration = 0;

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
      next.yaw !== eventYaw
      || next.pitch !== event.pitch
      || event.zoom !== 1
      || viewer.camera.zoom !== 1
    ) {
      enforceCameraState(next);
    }
    frame = next;
    onChange?.({ ...next });
  }

  function destroy(): void {
    loadGeneration += 1;
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
      const generation = loadGeneration;
      frame = { ...options.frame };
      bounds = options.bounds;
      onChange = options.onChange;
      root.classList.add("view360-container");
      canvas = document.createElement("canvas");
      canvas.className = "view360-canvas";
      canvas.setAttribute("aria-label", options.accessibleLabel);
      root.append(canvas);

      const projection = new CylindricalProjection({
        src: options.src,
        partial: true,
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
      if (generation !== loadGeneration || viewer !== createdViewer) {
        createdViewer.destroy();
        return;
      }
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
    cancelInteraction() {
      if (!viewer || !frame) return;
      const activeViewer = viewer;
      activeViewer.control.disable();
      void activeViewer.control.enable().then(() => {
        if (viewer === activeViewer && frame) enforceCameraState(frame);
      });
    },
    destroy,
  };
}
