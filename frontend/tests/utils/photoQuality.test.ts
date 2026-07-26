import type { StepRead as Step } from "@/client";
import { makeAlbumMedia, makeStep } from "../helpers";
import { PAGE_WIDTH_MM, PAGE_HEIGHT_MM, MM_PER_INCH } from "@/utils/pageSize";
import {
  computeDpi,
  dpiTier,
  mediaQuality,
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
    const dpi = computeDpi(4000, 3000, { widthFrac: 1, heightFrac: 1 }, "cover");
    expect(dpi).toBeCloseTo(4000 / (PAGE_WIDTH_MM / MM_PER_INCH), 0);
  });

  it("returns the minimum of width and height DPI", () => {
    const dpi = computeDpi(
      4000,
      1000,
      { widthFrac: 0.5, heightFrac: 1 },
      "cover",
    );
    const heightDpi = 1000 / (PAGE_HEIGHT_MM / MM_PER_INCH);
    expect(dpi).toBeCloseTo(heightDpi, 1);
  });

  it("uses the rendered image size for contained portraits", () => {
    const cell = { widthFrac: 1, heightFrac: 1 };
    const coverDpi = computeDpi(1688, 3000, cell, "cover");
    const containDpi = computeDpi(1688, 3000, cell, "contain");

    expect(coverDpi).toBeCloseTo(1688 / (PAGE_WIDTH_MM / MM_PER_INCH), 1);
    expect(containDpi).toBeCloseTo(3000 / (PAGE_HEIGHT_MM / MM_PER_INCH), 1);
  });
});

describe("dpiTier", () => {
  it.each<[number, DpiPreset, DpiTier]>([
    [0, undefined, "warning"],
    [Number.POSITIVE_INFINITY, undefined, "ok"],
    [0, "off", "ok"],
    [0, "print", "warning"],
    [Number.POSITIVE_INFINITY, "print", "ok"],
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

  function mediaMap(...items: ReturnType<typeof media>[]) {
    return new Map(items.map((item) => [item.name, item]));
  }

  it("counts low-res cover as warning", () => {
    const result = summarizeQuality(
      [],
      "lo.jpg",
      undefined,
      mediaMap(media("lo.jpg", 500, 400)),
    );
    expect(result.warning).toBe(1);
  });

  it("does not count warnings when warnings are off", () => {
    const result = summarizeQuality(
      [],
      "lo.jpg",
      undefined,
      mediaMap(media("lo.jpg", 500, 400)),
      "off",
    );
    expect(result).toEqual({ caution: 0, warning: 0 });
  });

  it("uses print-quality thresholds when requested", () => {
    const result = summarizeQuality(
      [],
      "medium.jpg",
      undefined,
      mediaMap(media("medium.jpg", 1800, 1800)),
      "print",
    );
    expect(result).toEqual({ caution: 1, warning: 0 });
  });

  it("does not warn for a contained full-page portrait with print thresholds", () => {
    const portrait = media("portrait.jpg", 1688, 3000);
    const steps = [
      makeStep({
        id: 1,
        pages: [{ kind: "grid", media: [portrait.name] }],
      }),
    ];

    const result = summarizeQuality(
      steps,
      undefined,
      undefined,
      mediaMap(portrait),
      "print",
    );

    expect(result).toEqual({ caution: 0, warning: 0 });
  });

  it("still warns when the same portrait is used as a full-bleed cover", () => {
    const portrait = media("portrait.jpg", 1688, 3000);

    const result = summarizeQuality(
      [],
      portrait.name,
      undefined,
      mediaMap(portrait),
      "print",
    );

    expect(result).toEqual({ caution: 0, warning: 1 });
  });

  it("handles cover photo appearing in both cover and step.cover", () => {
    const steps: Step[] = [
      makeStep({
        id: 1,
        cover: "lo.jpg",
        pages: [{ kind: "grid", media: ["lo.jpg"] }],
      }),
    ];
    const result = summarizeQuality(
      steps,
      "lo.jpg",
      undefined,
      mediaMap(media("lo.jpg", 800, 700)),
    );
    expect(result.warning).toBe(1);
    expect(result.caution).toBe(1);
  });

  it("applies orientation ordering before assigning cell fractions", () => {
    const portrait = media("portrait.jpg", 600, 900);
    const landscape = media("landscape.jpg", 800, 500);
    const steps = [
      makeStep({
        id: 1,
        pages: [
          {
            kind: "grid",
            media: ["landscape.jpg", "portrait.jpg", "landscape.jpg"],
          },
        ],
      }),
    ];
    const result = summarizeQuality(
      steps,
      undefined,
      undefined,
      mediaMap(portrait, landscape),
    );
    expect(result).toEqual({ caution: 0, warning: 0 });
  });

  it("lowers active panorama PPI as ordinary zoom crops its perspective viewport", () => {
    const wide = media("wide.jpg", 8000, 1000);
    wide.panorama = {
      status: "active",
      detection: "gpano",
      source_width: 8000,
      source_height: 1000,
      cropped_area_width: 8000,
      cropped_area_height: 1000,
      cropped_area_left: 0,
      cropped_area_top: 0,
      full_pano_width: 12000,
      full_pano_height: null,
      captured_fov: 240,
      yaw: 0,
      pitch: 0,
      perspective_fov: 60,
      zoom: 1,
      original_path: ".panoramas/originals/wide.jpg",
      revision: 1,
    };
    const cell = { widthFrac: 1, heightFrac: 1 };
    const unzoomed = mediaQuality(wide.name, cell, "cover", mediaMap(wide));
    wide.panorama.zoom = 2;
    const zoomed = mediaQuality(wide.name, cell, "cover", mediaMap(wide));

    expect(zoomed?.dpi).toBeLessThan(unzoomed?.dpi ?? Number.POSITIVE_INFINITY);
    expect(zoomed?.dpi).toBe(Math.round((unzoomed?.dpi ?? 0) / 2));
  });

  it("uses two A4 page widths for a panorama spread quality warning", () => {
    const wide = media("wide.jpg", 8000, 1000);
    wide.panorama = {
      status: "active",
      detection: "gpano",
      source_width: 8000,
      source_height: 1000,
      cropped_area_width: 8000,
      cropped_area_height: 1000,
      cropped_area_left: 0,
      cropped_area_top: 0,
      full_pano_width: 12000,
      full_pano_height: null,
      captured_fov: 240,
      yaw: 0,
      pitch: 0,
      perspective_fov: 60,
      zoom: 1,
      original_path: ".panoramas/originals/wide.jpg",
      revision: 1,
    };
    const steps = [
      makeStep({ id: 1, pages: [{ kind: "panorama_spread", media: [wide.name] }] }),
    ];

    expect(summarizeQuality(steps, undefined, undefined, mediaMap(wide), "print"))
      .toEqual({ caution: 0, warning: 1 });
  });
});
