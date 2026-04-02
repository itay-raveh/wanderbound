import ElevationProfile from "@/components/album/map/ElevationProfile.vue";
import { mountWithPlugins } from "../helpers";

function mountProfile(props: Record<string, unknown> = {}) {
  return mountWithPlugins(ElevationProfile, {
    props: {
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 200, dist: 5 },
        { elevation: 150, dist: 10 },
      ],
      accent: "#ff6600",
      isKm: true,
      ...props,
    },
  });
}

/** Extract numeric values from y-axis labels (x position = PAD.left - 2 = 18). */
function yTickValues(wrapper: ReturnType<typeof mountProfile>): number[] {
  return wrapper
    .findAll("text.axis-label")
    .filter((t) => t.attributes("x") === "18")
    .map((t) => Number(t.text()))
    .filter((n) => !isNaN(n));
}

/** Extract the x-coordinate of the last point in the line path. */
function lastLineX(wrapper: ReturnType<typeof mountProfile>): number {
  const d = wrapper.findAll("path").find((p) => p.attributes("fill") === "none")?.attributes("d") ?? "";
  const coords = d.match(/[\d.]+,[\d.]+/g) ?? [];
  return Number(coords.at(-1)?.split(",")[0]);
}

const SVG_W = 500;
const PAD_RIGHT = 8;
const PLOT_RIGHT = SVG_W - PAD_RIGHT;

describe("ElevationProfile", () => {
  it("renders nothing with < 2 points or zero distance", () => {
    expect(mountProfile({ points: [] }).find("svg").exists()).toBe(false);
    expect(mountProfile({ points: [{ elevation: 100, dist: 0 }] }).find("svg").exists()).toBe(false);
    expect(
      mountProfile({ points: [{ elevation: 100, dist: 0 }, { elevation: 200, dist: 0 }] })
        .find("svg").exists(),
    ).toBe(false);
  });

  it("hides the zero y-tick for sea-level hikes", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 0, dist: 0 },
        { elevation: 1400, dist: 60 },
      ],
    });
    const ticks = yTickValues(wrapper);
    expect(ticks).not.toContain(0);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
  });

  it("keeps all y-ticks for high-altitude hikes (no zero)", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 3000, dist: 0 },
        { elevation: 4500, dist: 40 },
      ],
    });
    const ticks = yTickValues(wrapper);
    expect(ticks.every((v) => v >= 3000)).toBe(true);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
  });

  it("data line extends close to the right edge of the plot", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 300, dist: 0 },
        { elevation: 800, dist: 30 },
        { elevation: 400, dist: 59.9 },
      ],
    });
    const endX = lastLineX(wrapper);
    // Last data point should be within 5% of the plot right edge
    expect(endX).toBeGreaterThan(PLOT_RIGHT * 0.95);
    expect(endX).toBeLessThanOrEqual(PLOT_RIGHT);
  });

  it("data line extends to the edge even when totalDistKm exceeds point data", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 500, dist: 50 },
      ],
      totalDistKm: 80, // metadata says 80km, but points only go to 50
    });
    const endX = lastLineX(wrapper);
    // Should scale to point data (50km), not metadata (80km)
    expect(endX).toBeGreaterThan(PLOT_RIGHT * 0.95);
  });

  it("converts to feet and miles when isKm is false", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 500, dist: 20 },
      ],
      isKm: false,
    });
    // Y-ticks should be in feet (100m ≈ 328ft, 500m ≈ 1640ft)
    const ticks = yTickValues(wrapper);
    expect(ticks.every((v) => v > 300)).toBe(true);
    // Unit labels
    expect(wrapper.find("text.unit-label").text()).toBe("ft");
    const xLabels = wrapper.findAll("text.axis-label").map((t) => t.text());
    expect(xLabels.some((t) => t.includes("mi"))).toBe(true);
  });

  it("x-axis labels stay within the SVG viewBox", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 200, dist: 59.9 },
      ],
    });
    const allLabels = wrapper.findAll("text.axis-label");
    for (const label of allLabels) {
      const x = Number(label.attributes("x"));
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(SVG_W);
    }
  });
});
