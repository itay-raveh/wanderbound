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

describe("ElevationProfile", () => {
  it("renders an SVG when given valid points", () => {
    const wrapper = mountProfile();
    const svg = wrapper.find("svg");
    expect(svg.exists()).toBe(true);
    expect(svg.classes()).toContain("elevation-chart");
  });

  it("renders nothing when points array is empty", () => {
    const wrapper = mountProfile({ points: [] });
    const svg = wrapper.find("svg");
    expect(svg.exists()).toBe(false);
  });

  it("renders nothing when only one point is provided", () => {
    const wrapper = mountProfile({
      points: [{ elevation: 100, dist: 0 }],
    });
    const svg = wrapper.find("svg");
    expect(svg.exists()).toBe(false);
  });

  it("renders the line path", () => {
    const wrapper = mountProfile();
    // The SVG should contain a path with the linePath (no fill, with stroke)
    const paths = wrapper.findAll("path");
    const linePath = paths.find(
      (p) => p.attributes("fill") === "none" && p.attributes("stroke") === "#ff6600",
    );
    expect(linePath).toBeTruthy();
  });

  it("renders the filled area path", () => {
    const wrapper = mountProfile();
    const paths = wrapper.findAll("path");
    // Area path has a gradient fill (url(#...))
    const areaPath = paths.find((p) =>
      p.attributes("fill")?.startsWith("url(#"),
    );
    expect(areaPath).toBeTruthy();
  });

  it("renders gradient defs", () => {
    const wrapper = mountProfile();
    const defs = wrapper.find("defs");
    expect(defs.exists()).toBe(true);

    const gradients = defs.findAll("linearGradient");
    expect(gradients.length).toBe(2); // elev-gradient and elev-bg-fade
  });

  it("renders Y-axis labels with elevation values", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 300, dist: 10 },
      ],
      isKm: true,
    });

    const texts = wrapper.findAll("text.axis-label");
    expect(texts.length).toBeGreaterThan(0);

    // Y labels should include min and max elevation values
    const textContents = texts.map((t) => t.text());
    // The max elevation (300) and min (100) should appear
    expect(textContents.some((t) => t.includes("300"))).toBe(true);
    expect(textContents.some((t) => t.includes("100"))).toBe(true);
  });

  it("renders Y-axis unit label", () => {
    const wrapper = mountProfile({ isKm: true });
    const unitLabel = wrapper.find("text.unit-label");
    expect(unitLabel.exists()).toBe(true);
    expect(unitLabel.text()).toBe("m");
  });

  it("renders ft unit when isKm is false", () => {
    const wrapper = mountProfile({ isKm: false });
    const unitLabel = wrapper.find("text.unit-label");
    expect(unitLabel.text()).toBe("ft");
  });

  it("converts elevation values to feet when isKm is false", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 200, dist: 10 },
      ],
      isKm: false,
    });

    const texts = wrapper.findAll("text.axis-label");
    const textContents = texts.map((t) => t.text());
    // 200m * 3.28084 = ~656ft, 100m * 3.28084 = ~328ft
    expect(textContents.some((t) => t.includes("656"))).toBe(true);
    expect(textContents.some((t) => t.includes("328"))).toBe(true);
  });

  it("renders X-axis labels", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 200, dist: 10 },
      ],
      totalDistKm: 10,
      isKm: true,
    });

    const texts = wrapper.findAll("text.axis-label");
    const textContents = texts.map((t) => t.text());
    // Should include "0" and "10.0 Km" (or similar)
    expect(textContents.some((t) => t.includes("0"))).toBe(true);
    expect(textContents.some((t) => t.includes("10.0"))).toBe(true);
  });

  it("renders grid lines for each Y label", () => {
    const wrapper = mountProfile();
    const lines = wrapper.findAll("line");
    // 3 y labels -> 3 grid lines
    expect(lines.length).toBe(3);
  });

  it("renders nothing when all points have the same distance (totalDist=0)", () => {
    const wrapper = mountProfile({
      points: [
        { elevation: 100, dist: 0 },
        { elevation: 200, dist: 0 },
      ],
    });
    const svg = wrapper.find("svg");
    expect(svg.exists()).toBe(false);
  });

  it("uses the accent color for the line stroke", () => {
    const wrapper = mountProfile({ accent: "#00ff00" });
    const paths = wrapper.findAll("path");
    const linePath = paths.find((p) => p.attributes("fill") === "none");
    expect(linePath?.attributes("stroke")).toBe("#00ff00");
  });

  it("sets correct viewBox dimensions", () => {
    const wrapper = mountProfile();
    const svg = wrapper.find("svg");
    // happy-dom lowercases SVG attributes; check both casing forms
    const viewBox = svg.attributes("viewBox") ?? svg.attributes("viewbox");
    expect(viewBox).toBe("0 0 500 100");
  });
});
