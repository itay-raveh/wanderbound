import { describe, it, expect } from "vitest";
import { useOverview } from "@/composables/useOverview";
import { makeStep } from "../helpers";
import type { SegmentOutline } from "@/client";

describe("useOverview", () => {
  it("computes total photos from step pages", () => {
    const steps = [
      makeStep({ pages: [["a.jpg", "b.jpg"], ["c.jpg"]] }),
      makeStep({ id: 2, pages: [["d.jpg"]] }),
    ];
    const overview = useOverview(steps, [], null, null);
    expect(overview.totalPhotos).toBe(4);
  });

  it("computes estimated distance from outlines with circuity", () => {
    const outlines: SegmentOutline[] = [
      {
        start_time: 0,
        end_time: 100,
        kind: "driving",
        timezone_id: "UTC",
        start_coord: [52.0, 4.0],
        end_coord: [52.1, 4.1],
      },
    ];
    const overview = useOverview([], outlines, null, null);
    expect(overview.estimatedDistanceKm).toBeGreaterThan(0);
  });

  it("uses exact distance when provided", () => {
    const overview = useOverview([], [], 1234.5, null);
    expect(overview.distanceKm).toBe(1234.5);
  });

  it("extracts unique countries", () => {
    const steps = [
      makeStep({
        location: {
          lat: 0,
          lon: 0,
          name: "A",
          detail: "NL",
          country_code: "nl",
        },
      }),
      makeStep({
        id: 2,
        location: {
          lat: 0,
          lon: 0,
          name: "B",
          detail: "NL",
          country_code: "nl",
        },
      }),
      makeStep({
        id: 3,
        location: {
          lat: 0,
          lon: 0,
          name: "C",
          detail: "BE",
          country_code: "be",
        },
      }),
    ];
    const overview = useOverview(steps, [], null, null);
    expect(overview.countries).toEqual([
      { code: "nl", detail: "NL" },
      { code: "be", detail: "BE" },
    ]);
  });

  it("excludes countries with code '00'", () => {
    const steps = [
      makeStep({ location: { lat: 0, lon: 0, name: "Unknown", detail: "Unknown", country_code: "00" } }),
      makeStep({ id: 2, location: { lat: 52.52, lon: 13.4, name: "Berlin", detail: "Germany", country_code: "DE" } }),
    ];
    const overview = useOverview(steps, [], null, null);
    expect(overview.countries).toEqual([{ code: "DE", detail: "Germany" }]);
  });

  it("finds coldest and hottest steps", () => {
    const steps = [
      makeStep({
        name: "Hot Place",
        weather: {
          day: { temp: 35, feels_like: 38, icon: "clear-day" },
          night: { temp: 25, feels_like: 27, icon: "clear-night" },
        },
      }),
      makeStep({
        id: 2,
        name: "Cold Place",
        weather: {
          day: { temp: 5, feels_like: 2, icon: "snow" },
          night: { temp: -3, feels_like: -8, icon: "snow" },
        },
      }),
    ];
    const overview = useOverview(steps, [], null, null);
    expect(overview.coldest).toEqual({ value: -8, stepName: "Cold Place" });
    expect(overview.hottest).toEqual({ value: 38, stepName: "Hot Place" });
  });

  it("finds furthest from home", () => {
    const steps = [
      makeStep({
        name: "Close",
        location: {
          lat: 52.0,
          lon: 4.0,
          name: "Close",
          detail: "NL",
          country_code: "nl",
        },
      }),
      makeStep({
        id: 2,
        name: "Far",
        location: {
          lat: -33.9,
          lon: 151.2,
          name: "Far",
          detail: "AU",
          country_code: "au",
        },
      }),
    ];
    const home = { lat: 52.37, lon: 4.9 };
    const overview = useOverview(steps, [], null, home);
    expect(overview.furthestFromHome).not.toBeNull();
    expect(overview.furthestFromHome!.stepName).toBe("Far");
    expect(overview.furthestFromHome!.distanceKm).toBeGreaterThan(10000);
  });

  it("returns null furthestFromHome when no home location", () => {
    const steps = [makeStep()];
    const overview = useOverview(steps, [], null, null);
    expect(overview.furthestFromHome).toBeNull();
  });
});
