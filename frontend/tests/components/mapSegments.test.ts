import { describe, expect, it, vi } from "vitest";
import { drawSegmentsAndMarkers } from "@/components/album/map/mapSegments";
import type { Segment } from "@/client";

function makeMap() {
  const container = document.createElement("div");
  return {
    addLayer: vi.fn(),
    addSource: vi.fn(),
    getContainer: vi.fn(() => container),
    getLayer: vi.fn(() => true),
    getSource: vi.fn(() => ({ setData: vi.fn() })),
    getStyle: vi.fn(() => ({ layers: [{ id: "seg-old" }] })),
    getTerrain: vi.fn(() => ({ source: "mapbox-dem" })),
    removeLayer: vi.fn(),
    removeSource: vi.fn(),
    setTerrain: vi.fn(),
  };
}

const segment: Segment = {
  uid: 1,
  aid: "a1",
  start_time: 0,
  end_time: 1,
  kind: "driving",
  timezone_id: "UTC",
  points: [
    { lat: 1, lon: 2, time: 0 },
    { lat: 3, lon: 4, time: 1 },
  ],
  route: null,
};

describe("drawSegmentsAndMarkers", () => {
  it("temporarily detaches terrain while replacing segment sources", () => {
    const map = makeMap();

    drawSegmentsAndMarkers(map as never, {
      segments: [segment],
      steps: [],
      albumId: "a1",
    });

    expect(map.setTerrain).toHaveBeenNthCalledWith(1, null);
    expect(map.removeSource).toHaveBeenCalledWith("seg-old");
    expect(map.setTerrain).toHaveBeenLastCalledWith({ source: "mapbox-dem" });
  });
});
