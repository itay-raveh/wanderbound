import { describe, it, expect } from "vitest";
import { computeOverview } from "@/composables/useOverview";
import { makeLocation, makeStep, makeWeather } from "../helpers";

describe("computeOverview", () => {
  it("excludes countries with code '00'", () => {
    const steps = [
      makeStep({
        location: makeLocation({
          name: "Unknown",
          detail: "Unknown",
          country_code: "00",
        }),
      }),
      makeStep({
        id: 2,
        location: makeLocation({
          lat: 52.52,
          lon: 13.4,
          name: "Berlin",
          detail: "Germany",
          country_code: "DE",
        }),
      }),
    ];
    const overview = computeOverview(steps, [], null, null);
    expect(overview.countries).toEqual([{ code: "DE", detail: "Germany" }]);
  });

  it("finds coldest and hottest steps", () => {
    const steps = [
      makeStep({
        name: "Hot Place",
        weather: makeWeather({
          day: { feels_like: 38 },
          night: { feels_like: 27 },
        }),
      }),
      makeStep({
        id: 2,
        name: "Cold Place",
        weather: makeWeather({
          day: { feels_like: 2 },
          night: { feels_like: -8 },
        }),
      }),
    ];
    const overview = computeOverview(steps, [], null, null);
    expect(overview.coldest).toMatchObject({ value: -8, isNight: true });
    expect(overview.coldest!.step.name).toBe("Cold Place");
    expect(overview.hottest).toMatchObject({ value: 38 });
    expect(overview.hottest!.step.name).toBe("Hot Place");
  });

  it("detects cold night on first step", () => {
    const steps = [
      makeStep({
        name: "Only Step",
        weather: makeWeather({
          day: { feels_like: 8 },
          night: { feels_like: -5 },
        }),
      }),
    ];
    const overview = computeOverview(steps, [], null, null);
    expect(overview.coldest).toMatchObject({ value: -5, isNight: true });
  });
});
