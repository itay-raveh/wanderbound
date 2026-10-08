import { describe, expect, it, vi } from "vitest";
import { drawSegmentsAndMarkers } from "@/components/album/map/mapSegments";
import { makeSegment } from "../helpers";

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

const segment = makeSegment({
  start_time: 0,
  end_time: 1,
  points: [
    { lat: 1, lon: 2, time: 0 },
    { lat: 3, lon: 4, time: 1 },
  ],
});

describe("drawSegmentsAndMarkers", () => {
  it.each([
    null,
    [],
    [
      [5.0, 52.24],
      [5.12, 52.09],
    ],
  ])(
    "keeps the complete driving trace visible with saved route %j",
    (route) => {
      const map = makeMap();
      const points = [
        { lon: 4.89, lat: 52.37, time: 0 },
        { lon: 5.0, lat: 52.24, time: 1 },
        { lon: 5.12, lat: 52.09, time: 2 },
      ];
      drawSegmentsAndMarkers(map as never, {
        segments: [
          makeSegment({ kind: "driving", points, route: route as never }),
        ],
        steps: [],
        albumId: "a1",
      });
      const source = map.addSource.mock.calls.find(
        ([id]) => id === "seg-drive",
      )?.[1];
      expect(source.data.geometry.coordinates).toEqual([
        points.map((p) => [p.lon, p.lat]),
      ]);
    },
  );

  it("retains a complete road route with ordinary endpoint snapping", () => {
    const map = makeMap();
    const route: [number, number][] = [
      [4.0001, 52.0],
      [4.06, 52.15],
      [4.1001, 52.1],
    ];
    drawSegmentsAndMarkers(map as never, {
      segments: [
        makeSegment({
          kind: "driving",
          route,
          points: [
            { lon: 4.0, lat: 52.0, time: 0 },
            { lon: 4.1, lat: 52.1, time: 1 },
          ],
        }),
      ],
      steps: [],
      albumId: "a1",
    });
    const source = map.addSource.mock.calls.find(
      ([id]) => id === "seg-drive",
    )?.[1];
    expect(source.data.geometry.coordinates).toEqual([route]);
  });

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
