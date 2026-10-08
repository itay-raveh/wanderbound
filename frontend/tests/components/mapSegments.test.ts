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

describe("drawSegmentsAndMarkers", () => {
  it.each([{ route: [] }, { route: [[5.12, 52.09]] }])(
    "keeps the complete driving trace visible with saved route $route",
    ({ route }) => {
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

  it.each(["snapped", "outlier", "loop", "directions", "tidied_endpoint"])(
    "retains a valid $0 road route",
    (shape) => {
      const map = makeMap();
      const route: [number, number][] = [
        [4.0001, 52.0],
        [4.06, 52.15],
        [4.1001, 52.1],
      ];
      const points = [
        { lon: 4.0, lat: 52.0, time: 0 },
        { lon: 4.06, lat: 52.15, time: 1 },
        { lon: 4.1, lat: 52.1, time: 2 },
      ];
      if (shape === "tidied_endpoint") points[0].lon = -74;
      if (shape === "outlier") points[1].lat = 53;
      if (shape === "loop") {
        points[2] = { ...points[0], time: 2 };
        route[2] = [...route[0]];
      }
      if (shape === "directions") {
        points.splice(1, 1);
        route[0][0] += 0.01;
      }
      drawSegmentsAndMarkers(map as never, {
        segments: [
          makeSegment({
            kind: "driving",
            route,
            points,
          }),
        ],
        steps: [],
        albumId: "a1",
      });
      const source = map.addSource.mock.calls.find(
        ([id]) => id === "seg-drive",
      )?.[1];
      expect(source.data.geometry.coordinates).toEqual([route]);
    },
  );
});
