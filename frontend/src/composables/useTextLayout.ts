import { computed, ref, watch, type ComputedRef, type Ref } from "vue";
import { ALLOWED_FONTS } from "@/utils/fonts";
import {
  PAGE_WIDTH_MM,
  PAGE_HEIGHT_MM,
  MM_PX,
  META_RATIO,
} from "@/utils/pageSize";
import { safeMarginMm } from "./useSafeMargin";

export interface TextPage {
  text: string;
  offset: number;
  lineIndex: number;
  direction: string;
}

interface TextLayout {
  pages: TextPage[]; // pages[0] = sidebar, pages[1..N] = continuation
}

const cache = new Map<string, TextLayout>();
const MAX_CACHE_SIZE = 200;

function cached(text: string, layout: TextLayout): TextLayout {
  if (cache.size >= MAX_CACHE_SIZE) {
    // Evict oldest entry (first inserted key)
    cache.delete(cache.keys().next().value!);
  }
  cache.set(text, layout);
  return layout;
}

// Debounced revision counter - bumped when fonts finish loading so reactive
// consumers (useTextLayout computeds) re-run. The loadingdone listener catches
// unicode-range fonts (e.g. Hebrew subsets) that load on demand after initial ready.
const fontsRevision = ref(0);
if (
  typeof document !== "undefined" &&
  document.fonts &&
  !(globalThis as Record<string, unknown>).__textLayoutFontsInit
) {
  (globalThis as Record<string, unknown>).__textLayoutFontsInit = true;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  const bumpRevision = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      fontsRevision.value++;
      cache.clear();
      layoutConfig = null;
    }, 100);
  };
  void document.fonts.ready.then(bumpRevision);
  document.fonts.addEventListener("loadingdone", ((e: FontFaceSetLoadEvent) => {
    if (
      e.fontfaces.some((f) =>
        (ALLOWED_FONTS as readonly string[]).includes(f.family),
      )
    )
      bumpRevision();
  }) as EventListener);
}

interface ZoneConfig {
  columnWidth: number;
  maxLines: number;
  font: string;
  lineHeightPx: number;
}

interface LayoutConfig {
  sidebar: ZoneConfig;
  continuation: ZoneConfig;
}

let layoutConfig: LayoutConfig | null = null;

// Invalidate layout config + cache when safe margin changes so text reflows.
watch(safeMarginMm, () => {
  layoutConfig = null;
  cache.clear();
});

function ensureConfig(): LayoutConfig {
  if (layoutConfig) return layoutConfig;

  const rootStyle = getComputedStyle(document.documentElement);
  const remPx = parseFloat(rootStyle.fontSize);

  const lineHeight = 1.65;

  const pageWidth = PAGE_WIDTH_MM * MM_PX;
  const pageHeight = PAGE_HEIGHT_MM * MM_PX;
  const smPx = safeMarginMm.value * MM_PX;
  const insetX = Math.max(
    parseFloat(rootStyle.getPropertyValue("--page-inset-x")) * remPx,
    smPx,
  );
  const insetY = Math.max(
    parseFloat(rootStyle.getPropertyValue("--page-inset-y")) * remPx,
    smPx,
  );
  const typeXs = parseFloat(rootStyle.getPropertyValue("--type-xs")) * remPx;
  const fontBody = rootStyle.getPropertyValue("--font-album-body").trim();

  // Both sidebar and continuation pages use the same column width and font.
  // Right padding is insetY (not insetX) - matches StepMetaPanel/StepDescriptionPage
  // padding shorthand: `insetY insetY insetY insetX` (vertical value reused as inner gap).
  const columnWidth = pageWidth * META_RATIO - insetX - insetY;
  const font = `${typeXs}px ${fontBody}`;
  const lineHeightPx = typeXs * lineHeight;

  // Sidebar: vertical space consumed by StepMetaPanel chrome above/below the
  // description slot. Excludes top padding (insetY) which varies with safe margin.
  //   silhouette row (5rem + gap-lg)      6.0rem
  //   name block (~2 lines + gap-lg)      3.0rem
  //   stats bar + progress + bot padding  7.0rem
  //   rounding headroom                   2.5rem
  //                                      ------
  //                                      ~18.5 rem
  // If StepMetaPanel layout changes, re-derive this constant.
  const META_PANEL_CHROME_REM = 18.5;
  const sidebarMaxLines = Math.floor(
    (pageHeight - META_PANEL_CHROME_REM * remPx - insetY) / lineHeightPx,
  );

  // Continuation pages: full page height with top + bottom padding.
  const continuationMaxLines = Math.floor(
    (pageHeight - 2 * insetY) / lineHeightPx,
  );

  layoutConfig = {
    sidebar: { columnWidth, maxLines: sidebarMaxLines, font, lineHeightPx },
    continuation: {
      columnWidth,
      maxLines: continuationMaxLines,
      font,
      lineHeightPx,
    },
  };
  return layoutConfig;
}

function paginateText(text: string, config: LayoutConfig): TextPage[] {
  text = text.replace(/\r\n?/g, "\n");
  const { columnWidth, font, lineHeightPx } = config.sidebar;
  const measure = document.createElement("div");
  measure.dir = "auto";
  // Keep the temporary measurement out of the document's scrollable area.
  measure.style.cssText = `position: fixed; visibility: hidden; pointer-events: none;
    left: 0; top: 0; width: ${columnWidth}px; font: ${font};
    line-height: ${lineHeightPx}px; white-space: pre-wrap;
    overflow-wrap: break-word; hyphens: none; tab-size: 8;`;
  const node = document.createTextNode("\u200b");
  measure.append(node);
  document.body.append(measure);
  const lineHeight = measure.getBoundingClientRect().height;
  // The sentinel gives a trailing newline its own line, as in a textarea.
  node.data = text + "\u200b";
  const direction = getComputedStyle(measure).direction;
  const bounds = measure.getBoundingClientRect();
  const lineCount = Math.round(bounds.height / lineHeight);
  const range = document.createRange();
  range.setStart(node, 0);
  const pages: TextPage[] = [];
  let offset = 0;
  for (let lineIndex = 0; lineIndex < lineCount; ) {
    const maxLines = pages.length
      ? config.continuation.maxLines
      : config.sidebar.maxLines;
    const nextLine = lineIndex + Math.max(1, maxLines);
    const bottom = bounds.top + nextLine * lineHeight;
    let low = nextLine >= lineCount ? text.length : offset;
    let high = text.length;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      range.setEnd(node, mid + 1);
      // Bounding rectangles discard the zero-width rectangles of blank lines.
      const rects = range.getClientRects();
      if ((rects[rects.length - 1]?.bottom ?? bounds.top) <= bottom)
        low = mid + 1;
      else high = mid;
    }
    pages.push({ text: text.slice(offset, low), offset, lineIndex, direction });
    offset = low;
    lineIndex = nextLine;
  }
  measure.remove();
  return pages;
}

export function layoutDescription(text: string): TextLayout {
  // Subscribe to reactive dependencies so computeds recompute on change
  void safeMarginMm.value;
  if (fontsRevision.value === 0) return { pages: [] };

  const hit = cache.get(text);
  if (hit) return hit;

  const config = ensureConfig();
  const pages = paginateText(text, config);

  return cached(text, { pages });
}

export function useTextLayout(
  description: Ref<string>,
): ComputedRef<TextLayout> {
  return computed(() => layoutDescription(description.value));
}
