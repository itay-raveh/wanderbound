export interface PanoramaFrameDraft {
  yaw: number;
  pitch: number;
  perspectiveFov: number;
  zoom: number;
}

interface PanoramaSourceGeometry {
  width: number;
  height: number;
}

interface PanoramaRange {
  min: number;
  max: number;
}

export interface PanoramaCameraBounds {
  yaw: PanoramaRange;
  pitch: PanoramaRange;
}

export const MIN_PERSPECTIVE_FOV = 1;
const MAX_PERSPECTIVE_FOV = 179;
export const MIN_PANORAMA_ZOOM = 1;

const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
const toDegrees = (radians: number) => (radians * 180) / Math.PI;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function capturedFov(geometry: PanoramaSourceGeometry): number {
  return Math.min(359, (90 * geometry.width) / geometry.height);
}

function verticalSourceBounds(
  geometry: PanoramaSourceGeometry,
  capturedFov: number,
): PanoramaRange {
  const { width, height } = geometry;
  const top = -height / 2;
  const bottom = top + height;
  const focalLength = width / toRadians(capturedFov);
  return {
    min: toDegrees(Math.atan(-bottom / focalLength)),
    max: toDegrees(Math.atan(-top / focalLength)),
  };
}

function horizontalFovForVerticalHalf(
  verticalHalfFov: number,
  aspectRatio: number,
): number {
  if (verticalHalfFov <= 0) return MIN_PERSPECTIVE_FOV;
  return toDegrees(
    2 * Math.atan(Math.tan(toRadians(verticalHalfFov)) * aspectRatio),
  );
}

function verticalHalfFov(perspectiveFov: number, aspectRatio: number): number {
  return toDegrees(
    Math.atan(Math.tan(toRadians(perspectiveFov / 2)) / aspectRatio),
  );
}

function maximumPerspective(
  capturedFov: number,
  sourceBounds: PanoramaRange,
  aspectRatio: number,
): number {
  const verticalMaximum = horizontalFovForVerticalHalf(
    (sourceBounds.max - sourceBounds.min) / 2,
    aspectRatio,
  );
  return Math.max(
    MIN_PERSPECTIVE_FOV,
    Math.min(MAX_PERSPECTIVE_FOV, capturedFov, verticalMaximum),
  );
}

export function panoramaCameraBounds(
  frame: PanoramaFrameDraft,
  geometry: PanoramaSourceGeometry,
  aspectRatio: number,
): PanoramaCameraBounds {
  const sourceFov = capturedFov(geometry);
  const sourceBounds = verticalSourceBounds(geometry, sourceFov);
  const perspectiveFov = clamp(
    frame.perspectiveFov,
    MIN_PERSPECTIVE_FOV,
    maximumPerspective(sourceFov, sourceBounds, aspectRatio),
  );
  const horizontalMargin = Math.max(0, (sourceFov - perspectiveFov) / 2);
  const verticalMargin = verticalHalfFov(perspectiveFov, aspectRatio);
  const pitch = {
    min: sourceBounds.min + verticalMargin,
    max: sourceBounds.max - verticalMargin,
  };
  if (pitch.min > pitch.max) {
    const center = (sourceBounds.min + sourceBounds.max) / 2;
    pitch.min = center;
    pitch.max = center;
  }
  return {
    yaw: { min: -horizontalMargin, max: horizontalMargin },
    pitch,
  };
}

export function clampPanoramaFrame(
  frame: PanoramaFrameDraft,
  geometry: PanoramaSourceGeometry,
  aspectRatio: number,
  maximumZoom = Number.MAX_SAFE_INTEGER,
): PanoramaFrameDraft {
  const sourceFov = capturedFov(geometry);
  const sourceBounds = verticalSourceBounds(geometry, sourceFov);
  const perspectiveFov = clamp(
    frame.perspectiveFov,
    MIN_PERSPECTIVE_FOV,
    maximumPerspective(sourceFov, sourceBounds, aspectRatio),
  );
  const normalized = { ...frame, perspectiveFov };
  const bounds = panoramaCameraBounds(normalized, geometry, aspectRatio);
  return {
    ...normalized,
    yaw: clamp(frame.yaw, bounds.yaw.min, bounds.yaw.max),
    pitch: clamp(frame.pitch, bounds.pitch.min, bounds.pitch.max),
    zoom: clamp(frame.zoom, MIN_PANORAMA_ZOOM, maximumZoom),
  };
}

export function autoFitPanoramaFrame(
  frame: PanoramaFrameDraft,
  geometry: PanoramaSourceGeometry,
  aspectRatio: number,
): PanoramaFrameDraft {
  const sourceFov = capturedFov(geometry);
  const sourceBounds = verticalSourceBounds(geometry, sourceFov);
  const centered = clampPanoramaFrame(
    {
      ...frame,
      perspectiveFov: MIN_PERSPECTIVE_FOV,
      zoom: MIN_PANORAMA_ZOOM,
    },
    geometry,
    aspectRatio,
  );
  const horizontalMaximum = sourceFov - 2 * Math.abs(centered.yaw);
  const availableVerticalHalf = Math.min(
    sourceBounds.max - centered.pitch,
    centered.pitch - sourceBounds.min,
  );
  const verticalMaximum = horizontalFovForVerticalHalf(
    availableVerticalHalf,
    aspectRatio,
  );
  return clampPanoramaFrame(
    {
      ...centered,
      perspectiveFov: Math.min(
        MAX_PERSPECTIVE_FOV,
        horizontalMaximum,
        verticalMaximum,
      ),
      zoom: MIN_PANORAMA_ZOOM,
    },
    geometry,
    aspectRatio,
  );
}
