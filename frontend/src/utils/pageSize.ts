/** Legacy trim dimensions remain the default for existing albums. */
export const PAGE_WIDTH_MM = 297;
export const PAGE_HEIGHT_MM = 210;
export const MM_PER_INCH = 25.4;
export const MM_PX = 96 / MM_PER_INCH;
export const META_RATIO = 0.45;

export interface PageSize {
  widthMm: number;
  heightMm: number;
}
export interface AlbumGeometrySettings {
  page_width_mm?: number | null;
  page_height_mm?: number | null;
  safe_margin_mm?: number | null;
  body_font?: string | null;
}
export const PAGE_PRESETS = [
  { id: "letter", label: "US Letter", widthMm: 279.4, heightMm: 215.9 },
  { id: "a4", label: "A4", widthMm: 297, heightMm: 210 },
  { id: "legal", label: "US Legal", widthMm: 355.6, heightMm: 215.9 },
  { id: "a3", label: "A3", widthMm: 420, heightMm: 297 },
] as const;

export function albumPageSize(album?: AlbumGeometrySettings): PageSize {
  return {
    widthMm: album?.page_width_mm ?? PAGE_WIDTH_MM,
    heightMm: album?.page_height_mm ?? PAGE_HEIGHT_MM,
  };
}

/** Match the API contract; bounds protect fixed-height chrome and render budgets. */
export function validatePageSize({ widthMm, heightMm }: PageSize): boolean {
  const ratio = widthMm / heightMm;
  return (
    Number.isFinite(widthMm) &&
    Number.isFinite(heightMm) &&
    widthMm >= 250 &&
    widthMm <= 420 &&
    heightMm >= 180 &&
    heightMm <= 297 &&
    ratio >= 1.25 &&
    ratio <= 1.8
  );
}

/** Physical sheets: interior trim + bleed, or two cover panels + spine + bleed. */
export function sheetSize(
  size: PageSize,
  bleedMm = 0,
  spineMm?: number,
): PageSize {
  return {
    widthMm:
      (spineMm == null ? size.widthMm : 2 * size.widthMm + spineMm) +
      2 * bleedMm,
    heightMm: size.heightMm + 2 * bleedMm,
  };
}

export function pageSizeStyle(size: PageSize): Record<string, string> {
  return {
    "--page-width": `${size.widthMm}mm`,
    "--page-height": `${size.heightMm}mm`,
    "--page-aspect": `${size.widthMm} / ${size.heightMm}`,
  };
}
