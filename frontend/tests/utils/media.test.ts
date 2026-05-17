import { describe, it, expect, vi } from "vitest";

vi.mock("@/client/client.gen", () => ({
  client: { getConfig: () => ({ baseUrl: "" }) },
}));

import { flagUrl, mediaThumbUrl, weatherIconUrl } from "@/utils/media";

describe("mediaThumbUrl", () => {
  it("returns the poster .jpg for a video, not the .mp4", () => {
    const url = mediaThumbUrl("clip.mp4", "aid-1", 200);
    expect(url).toBe("/api/v1/albums/aid-1/media/clip.jpg?w=200");
  });

  it("passes through .jpg paths unchanged", () => {
    const url = mediaThumbUrl("photo.jpg", "aid-1", 800);
    expect(url).toBe("/api/v1/albums/aid-1/media/photo.jpg?w=800");
  });

  it("adds an optional cache key after the thumbnail width", () => {
    const url = mediaThumbUrl("photo.jpg", "aid-1", 200, "2026-05-13T12:34:56Z");
    expect(url).toBe(
      "/api/v1/albums/aid-1/media/photo.jpg?w=200&d=2026-05-13T12%3A34%3A56Z",
    );
  });
});

describe("flagUrl", () => {
  it("returns a local PNG flag path for a country code", () => {
    expect(flagUrl("AR")).toBe("/flags/ar.png");
  });
});

describe("weatherIconUrl", () => {
  it("returns a local SVG weather icon path for an icon name", () => {
    expect(weatherIconUrl("partly-cloudy-day-rain")).toBe(
      "/weather-icons/partly-cloudy-day-rain.svg",
    );
  });
});
