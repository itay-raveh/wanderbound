import { describe, expect, it } from "vitest";
import {
  cropAspect,
  largestCrop,
  moveCrop,
  resizeCrop,
  rotateCrop,
  validCrop,
} from "@/utils/photoEdit";

describe("photo crop geometry", () => {
  it("keeps the crop filled through a full circle of rotation", () => {
    for (const [width, height] of [
      [1600, 900],
      [900, 1600],
    ]) {
      let crop = largestCrop(width, height, 0, width / height);
      for (const angle of [-180, -135, -90, -45, -1, 0, 1, 45, 90, 135, 180]) {
        crop = rotateCrop(crop, angle, width, height);
        expect(validCrop(crop, width, height), `${width}x${height} at ${angle}°`).toBe(true);
      }
    }
  });

  it("clamps a dragged crop and preserves the locked aspect", () => {
    const width = 1600;
    const height = 900;
    const crop = largestCrop(width, height, 33, width / height);
    const moved = moveCrop(crop, 1, 1, width, height);
    expect(validCrop(moved, width, height)).toBe(true);
    const resized = resizeCrop(moved, "se", 1, 1, width, height, width / height);
    expect(validCrop(resized, width, height)).toBe(true);
    expect(cropAspect(resized, width, height)).toBeCloseTo(width / height);
  });

  it("turns an uncropped landscape photo into portrait at 90 degrees", () => {
    const crop = largestCrop(1600, 900, 0, 1600 / 900);
    const turned = rotateCrop(crop, 90, 1600, 900);
    expect(cropAspect(turned, 1600, 900)).toBeCloseTo(900 / 1600);
    expect(validCrop(turned, 1600, 900)).toBe(true);
  });
});
