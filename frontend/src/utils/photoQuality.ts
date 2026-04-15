import type { Media, Step } from "@/client";
import type { PageFraction } from "@/utils/photoLayout";
import {
  PAGE_WIDTH_MM,
  PAGE_HEIGHT_MM,
  MM_PER_INCH,
  META_RATIO,
} from "@/utils/pageSize";
import {
  FULL_PAGE_FRACTION,
  enforceOrientationOrder,
  photoPageFraction,
  resolveLayoutClass,
} from "@/utils/photoLayout";
import { isPortraitByName } from "@/utils/media";

export type QualityTier = "ok" | "caution" | "warning";

export interface QualitySummary {
  caution: number;
  warning: number;
}

export interface PhotoQuality {
  tier: QualityTier;
  dpi: number;
}

const DPI_CAUTION_DEFAULT = 100;
const DPI_WARNING_DEFAULT = 75;
const DPI_CAUTION_UPGRADED = 150;
const DPI_WARNING_UPGRADED = 100;

export function dpiCautionThreshold(photosConnected: boolean): number {
  return photosConnected ? DPI_CAUTION_UPGRADED : DPI_CAUTION_DEFAULT;
}

export function dpiWarningThreshold(photosConnected: boolean): number {
  return photosConnected ? DPI_WARNING_UPGRADED : DPI_WARNING_DEFAULT;
}

export const COVER_FRACTION: PageFraction = FULL_PAGE_FRACTION;
export const PHOTO_PANEL_FRACTION: PageFraction = {
  widthFrac: 1 - META_RATIO,
  heightFrac: 1,
};

export function computeDpi(
  widthPx: number,
  heightPx: number,
  cell: PageFraction,
): number {
  const cellWidthInches = (cell.widthFrac * PAGE_WIDTH_MM) / MM_PER_INCH;
  const cellHeightInches = (cell.heightFrac * PAGE_HEIGHT_MM) / MM_PER_INCH;
  return Math.min(widthPx / cellWidthInches, heightPx / cellHeightInches);
}

export function dpiTier(
  dpi: number,
  photosConnected = false,
): QualityTier {
  if (dpi < dpiWarningThreshold(photosConnected)) return "warning";
  if (dpi < dpiCautionThreshold(photosConnected)) return "caution";
  return "ok";
}

export function mediaQuality(
  name: string,
  cell: PageFraction,
  mediaByName: ReadonlyMap<string, Media>,
  photosConnected = false,
): PhotoQuality | null {
  const m = mediaByName.get(name);
  if (!m) return null;
  const dpi = computeDpi(m.width, m.height, cell);
  return { tier: dpiTier(dpi, photosConnected), dpi: Math.round(dpi) };
}

export function summarizeQuality(
  steps: readonly Step[],
  frontCover: string | undefined,
  backCover: string | undefined,
  mediaByName: ReadonlyMap<string, Media>,
  photosConnected = false,
): QualitySummary {
  const summary: QualitySummary = { caution: 0, warning: 0 };

  function count(tier: QualityTier) {
    if (tier === "caution") summary.caution++;
    else if (tier === "warning") summary.warning++;
  }

  // Cover photos
  if (frontCover)
    count(
      mediaQuality(frontCover, COVER_FRACTION, mediaByName, photosConnected)
        ?.tier ?? "ok",
    );
  if (backCover)
    count(
      mediaQuality(backCover, COVER_FRACTION, mediaByName, photosConnected)
        ?.tier ?? "ok",
    );

  const isP = (name: string) => isPortraitByName(name, mediaByName);

  for (const step of steps) {
    // Step cover (right panel of StepMainPage)
    if (step.cover)
      count(
        mediaQuality(
          step.cover,
          PHOTO_PANEL_FRACTION,
          mediaByName,
          photosConnected,
        )?.tier ?? "ok",
      );

    // Photo pages
    for (const page of step.pages) {
      // Skip the cover photo (it's displayed on StepMainPage, not photo pages)
      const filtered = step.cover ? page.filter((p) => p !== step.cover) : page;
      if (filtered.length === 0) continue;

      const ordered = enforceOrientationOrder(filtered, isP);
      const layoutClass = resolveLayoutClass(ordered, isP);
      for (let i = 0; i < ordered.length; i++) {
        const cell = photoPageFraction(layoutClass, i);
        count(
          mediaQuality(ordered[i], cell, mediaByName, photosConnected)?.tier ??
            "ok",
        );
      }
    }
  }

  return summary;
}
