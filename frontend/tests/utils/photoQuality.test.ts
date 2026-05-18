import type { StepRead as Step } from "@/client";
import { makeAlbumMedia, makeStep } from "../helpers";
import { PAGE_WIDTH_MM, PAGE_HEIGHT_MM, MM_PER_INCH } from "@/utils/pageSize";
import {
  DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  DEMO_MEDIA_RESOLUTION_WARNING_PRESET,
  computeDpi,
  dpiTier,
  summarizeQuality,
} from "@/utils/photoQuality";
import {
  photoPageFraction,
  enforceOrientationOrder,
} from "@/utils/photoLayout";

type DpiPreset = Parameters<typeof dpiTier>[1];
type DpiTier = ReturnType<typeof dpiTier>;

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

describe("dpiTier", () => {
  it("defaults normal albums to relaxed warnings and demo albums to off", () => {
    expect(DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET).toBe("relaxed");
    expect(DEMO_MEDIA_RESOLUTION_WARNING_PRESET).toBe("off");
  });

  it.each<[number, DpiPreset, DpiTier]>([
    [100, undefined, "ok"],
    [300, undefined, "ok"],
    [99, undefined, "caution"],
    [75, undefined, "caution"],
    [74, undefined, "warning"],
    [50, undefined, "warning"],
    [1, "off", "ok"],
    [50, "off", "ok"],
    [300, "print", "ok"],
    [450, "print", "ok"],
    [299, "print", "caution"],
    [150, "print", "caution"],
    [149, "print", "warning"],
    [50, "print", "warning"],
  ])("classifies %s dpi with %s preset as %s", (dpi, preset, expected) => {
    expect(dpiTier(dpi, preset)).toBe(expected);
  });
});

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
    expect(photoPageFraction("layout-2p-1l", 0)).toEqual({
      widthFrac: 0.5,
      heightFrac: 0.5,
    });
    expect(photoPageFraction("layout-2p-1l", 2)).toEqual({
      widthFrac: 1,
      heightFrac: 0.5,
    });
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

describe("enforceOrientationOrder", () => {
  const isP = (name: string) => name.startsWith("p");

  it("moves the single portrait to front for 1P+2L", () => {
    expect(enforceOrientationOrder(["l1", "p1", "l2"], isP)).toEqual([
      "p1",
      "l1",
      "l2",
    ]);
  });

  it("keeps portraits first and landscape last for 2P+1L", () => {
    expect(enforceOrientationOrder(["l1", "p1", "p2"], isP)).toEqual([
      "p1",
      "p2",
      "l1",
    ]);
  });
});

describe("summarizeQuality", () => {
  function media(name: string, width: number, height: number) {
    return makeAlbumMedia({ name, width, height });
  }

  it("counts low-res cover as warning", () => {
    const mediaMap = new Map([["lo.jpg", media("lo.jpg", 500, 400)]]);
    const result = summarizeQuality([], "lo.jpg", undefined, mediaMap);
    expect(result.warning).toBe(1);
  });

  it("does not count warnings when warnings are off", () => {
    const mediaMap = new Map([["lo.jpg", media("lo.jpg", 500, 400)]]);
    const result = summarizeQuality([], "lo.jpg", undefined, mediaMap, "off");
    expect(result).toEqual({ caution: 0, warning: 0 });
  });

  it("uses print-quality thresholds when requested", () => {
    const mediaMap = new Map([["medium.jpg", media("medium.jpg", 1800, 1800)]]);
    const result = summarizeQuality(
      [],
      "medium.jpg",
      undefined,
      mediaMap,
      "print",
    );
    expect(result).toEqual({ caution: 1, warning: 0 });
  });

  it("handles cover photo appearing in both cover and step.cover", () => {
    const mediaMap = new Map([["lo.jpg", media("lo.jpg", 800, 700)]]);
    const steps: Step[] = [
      makeStep({ id: 1, cover: "lo.jpg", pages: [["lo.jpg"]] }),
    ];
    const result = summarizeQuality(steps, "lo.jpg", undefined, mediaMap);
    expect(result.warning).toBe(1);
    expect(result.caution).toBe(1);
  });

  it("applies orientation ordering before assigning cell fractions", () => {
    const portrait = media("portrait.jpg", 600, 900);
    const landscape = media("landscape.jpg", 800, 500);
    const mediaMap = new Map([
      [portrait.name, portrait],
      [landscape.name, landscape],
    ]);
    const steps = [
      makeStep({
        id: 1,
        pages: [["landscape.jpg", "portrait.jpg", "landscape.jpg"]],
      }),
    ];
    const result = summarizeQuality(steps, undefined, undefined, mediaMap);
    expect(result).toEqual({ caution: 0, warning: 0 });
  });
});
