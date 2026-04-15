export interface PageFraction {
  widthFrac: number;
  heightFrac: number;
}

export const FULL_PAGE_FRACTION: PageFraction = { widthFrac: 1, heightFrac: 1 };

type FractionSpec = { uniform: PageFraction } | { byCellIndex: PageFraction[] };

/** Hero-left + stacked-right: 1 cell spans full height, remaining cells share the right half. */
const HERO_LEFT_STACKED: PageFraction[] = [
  { widthFrac: 0.5, heightFrac: 1 },
  { widthFrac: 0.5, heightFrac: 0.5 },
  { widthFrac: 0.5, heightFrac: 0.5 },
];

const LAYOUT_FRACTIONS: Record<string, FractionSpec> = {
  // 1 photo
  "layout-1p-0l": { uniform: FULL_PAGE_FRACTION },
  "layout-0p-1l": { uniform: FULL_PAGE_FRACTION },

  // 2 photos
  "layout-0p-2l": { uniform: { widthFrac: 0.5, heightFrac: 1 } },
  "layout-1p-1l": { uniform: { widthFrac: 0.5, heightFrac: 1 } },
  "layout-2p-0l": { uniform: { widthFrac: 0.5, heightFrac: 1 } },

  // 3 photos - same orientation
  "layout-3p-0l": { uniform: { widthFrac: 1 / 3, heightFrac: 1 } },
  "layout-0p-3l": { byCellIndex: HERO_LEFT_STACKED },

  // 3 photos - mixed
  "layout-1p-2l": { byCellIndex: HERO_LEFT_STACKED },
  "layout-2p-1l": {
    byCellIndex: [
      { widthFrac: 0.5, heightFrac: 0.5 },
      { widthFrac: 0.5, heightFrac: 0.5 },
      { widthFrac: 1, heightFrac: 0.5 },
    ],
  },

  // 4 photos
  "layout-0p-4l": { uniform: { widthFrac: 0.5, heightFrac: 0.5 } },
  "layout-2p-2l": { uniform: { widthFrac: 0.5, heightFrac: 0.5 } },
  "layout-3p-1l": { uniform: { widthFrac: 0.5, heightFrac: 0.5 } },
  "layout-4p-0l": { uniform: { widthFrac: 0.5, heightFrac: 0.5 } },
  "layout-1p-3l": {
    byCellIndex: [
      { widthFrac: 0.4, heightFrac: 1 },
      { widthFrac: 0.6, heightFrac: 1 / 3 },
      { widthFrac: 0.6, heightFrac: 1 / 3 },
      { widthFrac: 0.6, heightFrac: 1 / 3 },
    ],
  },

  // 5+ photos
  "layout-5": {
    byCellIndex: [
      { widthFrac: 2 / 3, heightFrac: 1 },
      { widthFrac: 1 / 3, heightFrac: 0.5 },
      { widthFrac: 1 / 3, heightFrac: 0.5 },
      { widthFrac: 1 / 3, heightFrac: 0.5 },
      { widthFrac: 1 / 3, heightFrac: 0.5 },
    ],
  },
  "layout-6": {
    byCellIndex: [
      { widthFrac: 2 / 3, heightFrac: 1 },
      { widthFrac: 1 / 3, heightFrac: 1 / 3 },
      { widthFrac: 1 / 3, heightFrac: 1 / 3 },
      { widthFrac: 1 / 3, heightFrac: 1 / 3 },
      { widthFrac: 1 / 3, heightFrac: 1 / 3 },
      { widthFrac: 1 / 3, heightFrac: 1 / 3 },
    ],
  },
};

export function photoPageFraction(
  layoutClass: string,
  cellIndex: number,
): PageFraction {
  const spec = LAYOUT_FRACTIONS[layoutClass];
  if (!spec) return FULL_PAGE_FRACTION;
  if ("uniform" in spec) return spec.uniform;
  return (
    spec.byCellIndex[cellIndex] ?? spec.byCellIndex[spec.byCellIndex.length - 1]
  );
}

/**
 * Mixed layouts depend on orientation ordering:
 * - 1P+2L / 1P+3L: portrait must be first (spans all rows on the left).
 * - 2P+1L: landscape must be last (spans full bottom row).
 */
export function enforceOrientationOrder(
  page: readonly string[],
  isPortraitByName: (name: string) => boolean,
): string[] {
  if (page.length !== 3 && page.length !== 4) return [...page];
  const portraits = page.filter(isPortraitByName);
  const landscapes = page.filter((m) => !isPortraitByName(m));
  if (portraits.length === 1) return [portraits[0], ...landscapes];
  if (portraits.length === 2 && page.length === 3)
    return [...portraits, landscapes[0]];
  return [...page];
}

export function resolveLayoutClass(
  page: readonly string[],
  isPortraitByName: (name: string) => boolean,
): string {
  if (page.length >= 5) return `layout-${page.length}`;
  const p = page.filter(isPortraitByName).length;
  const l = page.length - p;
  return `layout-${p}p-${l}l`;
}
