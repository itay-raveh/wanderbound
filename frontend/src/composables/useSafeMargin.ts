import { ref } from "vue";
import { interiorBleedMm } from "@/composables/usePrintSettings";
import { MM_PX } from "@/utils/pageSize";

/**
 * Album-level safe margin (mm) - the print trim danger zone.
 * Set by AlbumViewer from `album.safe_margin_mm`, consumed by map
 * components (fitBounds padding) and useTextLayout (column reflow).
 */
export const safeMarginMm = ref(0);

/** Map padding starts at the bleed edge, outside the finished page. */
export function mapSafeInsetPx(): number {
  return Math.round((safeMarginMm.value + interiorBleedMm.value) * MM_PX);
}

export function setSafeMargin(mm: number) {
  if (safeMarginMm.value === mm) return;
  safeMarginMm.value = mm;
}
