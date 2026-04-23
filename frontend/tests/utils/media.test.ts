import { describe, it, expect, vi } from "vitest";

vi.mock("@/client/client.gen", () => ({
  client: { getConfig: () => ({ baseUrl: "" }) },
}));

import { mediaThumbUrl } from "@/utils/media";

describe("mediaThumbUrl", () => {
  it("returns the poster .jpg for a video, not the .mp4", () => {
    const url = mediaThumbUrl("clip.mp4", "aid-1", 200);
    expect(url).toBe("/api/v1/albums/aid-1/media/clip.jpg?w=200");
  });

  it("passes through .jpg paths unchanged", () => {
    const url = mediaThumbUrl("photo.jpg", "aid-1", 800);
    expect(url).toBe("/api/v1/albums/aid-1/media/photo.jpg?w=800");
  });
});
