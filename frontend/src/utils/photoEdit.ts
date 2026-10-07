import type { PhotoEdit } from "@/client";

export type CropCorner = "nw" | "ne" | "sw" | "se";

export function rotatedSize(width: number, height: number, angle: number) {
  const radians = (angle * Math.PI) / 180;
  const cosine = Math.abs(Math.cos(radians));
  const sine = Math.abs(Math.sin(radians));
  return {
    width: width * cosine + height * sine,
    height: width * sine + height * cosine,
  };
}

export function cropAspect(
  crop: PhotoEdit,
  width: number,
  height: number,
): number {
  const size = rotatedSize(width, height, crop.angle);
  return (crop.width * size.width) / (crop.height * size.height);
}

export function validCrop(
  crop: PhotoEdit,
  width: number,
  height: number,
): boolean {
  if (
    crop.x < 0 ||
    crop.y < 0 ||
    crop.width <= 0 ||
    crop.height <= 0 ||
    crop.x + crop.width > 1.000001 ||
    crop.y + crop.height > 1.000001
  )
    return false;
  const size = rotatedSize(width, height, crop.angle);
  const angle = (crop.angle * Math.PI) / 180;
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  for (const x of [crop.x, crop.x + crop.width]) {
    for (const y of [crop.y, crop.y + crop.height]) {
      const dx = (x - 0.5) * size.width;
      const dy = (y - 0.5) * size.height;
      const sx = dx * cosine + dy * sine;
      const sy = -dx * sine + dy * cosine;
      if (Math.abs(sx) > width / 2 + 0.001 || Math.abs(sy) > height / 2 + 0.001)
        return false;
    }
  }
  return true;
}

export function largestCrop(
  width: number,
  height: number,
  angle: number,
  aspect: number,
): PhotoEdit {
  const radians = (angle * Math.PI) / 180;
  const cosine = Math.abs(Math.cos(radians));
  const sine = Math.abs(Math.sin(radians));
  const halfHeight = Math.min(
    width / (2 * (aspect * cosine + sine)),
    height / (2 * (aspect * sine + cosine)),
  );
  const size = rotatedSize(width, height, angle);
  const inset = sine > 0.000001 && cosine > 0.000001 ? 0.996 : 1;
  const cropWidth = (2 * halfHeight * aspect * inset) / size.width;
  const cropHeight = (2 * halfHeight * inset) / size.height;
  return {
    angle,
    x: (1 - cropWidth) / 2,
    y: (1 - cropHeight) / 2,
    width: cropWidth,
    height: cropHeight,
  };
}

function interpolate(a: PhotoEdit, b: PhotoEdit, fraction: number): PhotoEdit {
  return {
    angle: b.angle,
    x: a.x + (b.x - a.x) * fraction,
    y: a.y + (b.y - a.y) * fraction,
    width: a.width + (b.width - a.width) * fraction,
    height: a.height + (b.height - a.height) * fraction,
  };
}

function clampChange(
  current: PhotoEdit,
  target: PhotoEdit,
  width: number,
  height: number,
): PhotoEdit {
  if (validCrop(target, width, height)) return target;
  let low = 0;
  let high = 1;
  for (let i = 0; i < 24; i++) {
    const middle = (low + high) / 2;
    if (validCrop(interpolate(current, target, middle), width, height))
      low = middle;
    else high = middle;
  }
  return interpolate(current, target, low);
}

export function moveCrop(
  crop: PhotoEdit,
  dx: number,
  dy: number,
  width: number,
  height: number,
): PhotoEdit {
  return clampChange(
    crop,
    { ...crop, x: crop.x + dx, y: crop.y + dy },
    width,
    height,
  );
}

export function resizeCrop(
  crop: PhotoEdit,
  corner: CropCorner,
  x: number,
  y: number,
  width: number,
  height: number,
  lockedAspect?: number,
): PhotoEdit {
  const anchorX = corner.endsWith("w") ? crop.x + crop.width : crop.x;
  const anchorY = corner.startsWith("n") ? crop.y + crop.height : crop.y;
  const signX = corner.endsWith("w") ? -1 : 1;
  const signY = corner.startsWith("n") ? -1 : 1;
  let nextWidth = Math.max(0.02, (x - anchorX) * signX);
  let nextHeight = Math.max(0.02, (y - anchorY) * signY);
  if (lockedAspect) {
    const size = rotatedSize(width, height, crop.angle);
    const normalizedAspect = (lockedAspect * size.height) / size.width;
    nextWidth = Math.min(nextWidth, nextHeight * normalizedAspect);
    nextHeight = nextWidth / normalizedAspect;
  }
  const target = {
    ...crop,
    x: signX < 0 ? anchorX - nextWidth : anchorX,
    y: signY < 0 ? anchorY - nextHeight : anchorY,
    width: nextWidth,
    height: nextHeight,
  };
  return clampChange(crop, target, width, height);
}

export function zoomCrop(
  crop: PhotoEdit,
  zoom: number,
  width: number,
  height: number,
): PhotoEdit {
  const max = largestCrop(
    width,
    height,
    crop.angle,
    cropAspect(crop, width, height),
  );
  const target = {
    ...max,
    width: max.width / zoom,
    height: max.height / zoom,
  };
  target.x = (1 - target.width) / 2;
  target.y = (1 - target.height) / 2;
  return moveCrop(
    target,
    crop.x + crop.width / 2 - 0.5,
    crop.y + crop.height / 2 - 0.5,
    width,
    height,
  );
}

export function rotateCrop(
  crop: PhotoEdit,
  angle: number,
  width: number,
  height: number,
  lockedAspect?: number,
): PhotoEdit {
  const oldAspect = cropAspect(crop, width, height);
  const max = largestCrop(width, height, crop.angle, oldAspect);
  const zoom = max.width / crop.width;
  const newSize = rotatedSize(width, height, angle);
  const aspect =
    lockedAspect ??
    (crop.width / crop.height) * (newSize.width / newSize.height);
  const next = largestCrop(width, height, angle, aspect);
  const resized = zoomCrop(next, zoom, width, height);
  const oldSize = rotatedSize(width, height, crop.angle);
  const oldRadians = (crop.angle * Math.PI) / 180;
  const dx = (crop.x + crop.width / 2 - 0.5) * oldSize.width;
  const dy = (crop.y + crop.height / 2 - 0.5) * oldSize.height;
  const sourceX = dx * Math.cos(oldRadians) + dy * Math.sin(oldRadians);
  const sourceY = -dx * Math.sin(oldRadians) + dy * Math.cos(oldRadians);
  const radians = (angle * Math.PI) / 180;
  const newX =
    (sourceX * Math.cos(radians) - sourceY * Math.sin(radians)) / newSize.width;
  const newY =
    (sourceX * Math.sin(radians) + sourceY * Math.cos(radians)) /
    newSize.height;
  return moveCrop(resized, newX, newY, width, height);
}
