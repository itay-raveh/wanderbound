import { describe, it, expect } from "vitest";
import { computeOverview } from "@/composables/useOverview";
import { makeStep } from "../helpers";

describe("computeOverview", () => {
  it("excludes countries with code '00'", () => {
    const steps = [
      makeStep({ location: { lat: 0, lon: 0, name: "Unknown", detail: "Unknown", country_code: "00" } }),
      makeStep({ id: 2, location: { lat: 52.52, lon: 13.4, name: "Berlin", detail: "Germany", country_code: "DE" } }),
    ];
    const overview = computeOverview(steps, [], null, null);
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
        weather: {
          day: { temp: 10, feels_like: 8, icon: "cloudy" },
          night: { temp: -2, feels_like: -5, icon: "snow" },
        },
      }),
    ];
    const overview = computeOverview(steps, [], null, null);
    expect(overview.coldest).toMatchObject({ value: -5, isNight: true });
  });

});
