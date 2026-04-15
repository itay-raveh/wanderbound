import type { Media, Step } from "@/client";
import { PAGE_WIDTH_MM, PAGE_HEIGHT_MM, MM_PER_INCH } from "@/utils/pageSize";
import { computeDpi, dpiTier, summarizeQuality } from "@/utils/photoQuality";
import {
  photoPageFraction,
  enforceOrientationOrder,
} from "@/utils/photoLayout";

// -- computeDpi --

describe("computeDpi", () => {
  it("computes DPI for a full-page photo", () => {
    const dpi = computeDpi(4000, 3000, { widthFrac: 1, heightFrac: 1 });
    expect(dpi).toBeCloseTo(4000 / (PAGE_WIDTH_MM / MM_PER_INCH), 0);
  });

  it("returns the minimum of width and height DPI", () => {
    const dpi = computeDpi(4000, 1000, { widthFrac: 0.5, heightFrac: 1 });
    const heightDpi = 1000 / (PAGE_HEIGHT_MM / MM_PER_INCH);
    expect(dpi).toBeCloseTo(heightDpi, 1);
  });

});

// -- dpiTier --

describe("dpiTier", () => {
  it("classifies >= 100 as ok", () => {
    expect(dpiTier(100)).toBe("ok");
    expect(dpiTier(300)).toBe("ok");
  });

  it("classifies 75-99 as caution", () => {
    expect(dpiTier(99)).toBe("caution");
    expect(dpiTier(75)).toBe("caution");
  });

  it("classifies < 75 as warning", () => {
    expect(dpiTier(74)).toBe("warning");
    expect(dpiTier(50)).toBe("warning");
  });
});

// -- photoPageFraction --

describe("photoPageFraction", () => {
  it("returns full page for single-photo layouts", () => {
    for (const cls of ["layout-1p-0l", "layout-0p-1l"]) {
      const f = photoPageFraction(cls, 0);
      expect(f).toEqual({ widthFrac: 1, heightFrac: 1 });
    }
  });

  it("handles 1p-2l mixed layout (portrait spans, landscapes half)", () => {
    const f0 = photoPageFraction("layout-1p-2l", 0);
    expect(f0).toEqual({ widthFrac: 0.5, heightFrac: 1 });
    const f1 = photoPageFraction("layout-1p-2l", 1);
    expect(f1).toEqual({ widthFrac: 0.5, heightFrac: 0.5 });
  });

  it("handles 2p-1l mixed layout (portraits quarter, landscape full-width half)", () => {
    expect(photoPageFraction("layout-2p-1l", 0)).toEqual({ widthFrac: 0.5, heightFrac: 0.5 });
    expect(photoPageFraction("layout-2p-1l", 2)).toEqual({ widthFrac: 1, heightFrac: 0.5 });
  });

  it("handles layout-5 (2/3 hero + 1/3 small)", () => {
    const hero = photoPageFraction("layout-5", 0);
    expect(hero.widthFrac).toBeCloseTo(2 / 3, 5);
    expect(hero.heightFrac).toBe(1);
    const small = photoPageFraction("layout-5", 1);
    expect(small.widthFrac).toBeCloseTo(1 / 3, 5);
    expect(small.heightFrac).toBe(0.5);
  });
});

// -- enforceOrientationOrder --

describe("enforceOrientationOrder", () => {
  const isP = (name: string) => name.startsWith("p");

  it("moves the single portrait to front for 1P+2L", () => {
    expect(enforceOrientationOrder(["l1", "p1", "l2"], isP)).toEqual(["p1", "l1", "l2"]);
  });

  it("keeps portraits first and landscape last for 2P+1L", () => {
    expect(enforceOrientationOrder(["l1", "p1", "p2"], isP)).toEqual(["p1", "p2", "l1"]);
  });
});

// -- summarizeQuality --

describe("summarizeQuality", () => {
  function media(name: string, width: number, height: number): Media {
    return { name, width, height };
  }

  function step(overrides: Partial<Step> & { id: number }): Step {
    return {
      uid: 1,
      aid: "trip",
      name: "Step",
      description: "",
      cover: null,
      pages: [],
      unused: [],
      timestamp: 0,
      timezone_id: "UTC",
      location: { city: "", country: "", country_code: "US" },
      elevation: 0,
      weather: { icon: "clear-day", high: 20, low: 10, code: 0, condition: "Clear" },
      datetime: "2024-01-01T00:00:00Z",
      ...overrides,
    };
  }

  it("counts low-res cover as warning", () => {
    // 500px on full 297mm page → ~43 DPI → warning
    const mediaMap = new Map([["lo.jpg", media("lo.jpg", 500, 400)]]);
    const result = summarizeQuality([], "lo.jpg", undefined, mediaMap);
    expect(result.warning).toBe(1);
  });

  it("handles cover photo appearing in both cover and step.cover", () => {
    // 800×700: front cover min(68,85)=68 → warning; side panel min(124,85)=85 → caution
    const mediaMap = new Map([["lo.jpg", media("lo.jpg", 800, 700)]]);
    const steps = [step({ id: 1, cover: "lo.jpg", pages: [["lo.jpg"]] })];
    // Front cover (full bleed) + step cover (side panel) - the page entry is
    // filtered out because it matches step.cover
    const result = summarizeQuality(steps, "lo.jpg", undefined, mediaMap);
    expect(result.warning).toBe(1);
    expect(result.caution).toBe(1);
  });

  it("applies orientation ordering before assigning cell fractions", () => {
    // 1p-2l layout: portrait spans full height (left), landscapes are half-height (right).
    // A low-res landscape in the raw data at index 0 should be evaluated in its
    // actual (half-height) cell after orientation reordering, not the portrait cell.
    const portrait = media("portrait.jpg", 600, 900); // portrait
    const landscape = media("landscape.jpg", 800, 500); // landscape - low res
    const mediaMap = new Map([
      [portrait.name, portrait],
      [landscape.name, landscape],
    ]);
    // Raw order: landscape first - without enforceOrientationOrder this assigns
    // the landscape the portrait's full-height cell (inflating its DPI).
    const steps = [step({ id: 1, pages: [["landscape.jpg", "portrait.jpg", "landscape.jpg"]] })];
    const result = summarizeQuality(steps, undefined, undefined, mediaMap);
    // After reordering: [portrait, landscape, landscape] in layout-1p-2l.
    // Portrait (600×900) in cell {0.5, 1}: min(600/(148.5/25.4), 900/(210/25.4)) ≈ min(103, 109) = 103 → ok
    // Landscape (800×500) in cell {0.5, 0.5}: min(800/(148.5/25.4), 500/(105/25.4)) ≈ min(137, 121) = 121 → ok
    // Both landscapes are the same media at 121 DPI → ok. All photos are ok.
    expect(result).toEqual({ caution: 0, warning: 0 });
  });
});
