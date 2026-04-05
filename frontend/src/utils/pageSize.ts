/** A4 landscape — single source of truth for page dimensions. */
export const PAGE_WIDTH_MM = 297;
export const PAGE_HEIGHT_MM = 210;

const MM_PER_INCH = 25.4;

/** mm → CSS px conversion factor (96 DPI). */
export const MM_PX = 96 / MM_PER_INCH;

/** Meta-panel fraction of page width. App.vue sets --meta-ratio from this. */
export const META_RATIO = 0.45;
