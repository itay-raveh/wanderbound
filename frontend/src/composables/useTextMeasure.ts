import { computed, ref, type ComputedRef, type Ref } from "vue";
import { layoutItemsFromString, breakLines, positionItems } from "tex-linebreak";
import { ALLOWED_FONTS } from "@/utils/fonts";

export type DescriptionType = "short" | "long" | "extra-long";

export interface JustifiedLine {
  text: string;
  wordSpacing: number; // CSS word-spacing delta in px (0 = default spacing)
}

interface TextLayout {
  type: DescriptionType;
  mainLines: JustifiedLine[] | null;
  continuationLines: JustifiedLine[][];
}

// --- Measurement cache (cleared when fonts finish loading) ---
const cache = new Map<string, TextLayout>();

function cached(text: string, layout: TextLayout): TextLayout {
  cache.set(text, layout);
  return layout;
}

// --- Font readiness tracking (reactive - triggers recomputation in computed contexts) ---
// Revision counter bumped when fonts finish loading. The loadingdone listener handles
// unicode-range fonts (e.g. Hebrew subsets) that load on demand after initial ready.
// Debounced so rapid successive loads (multiple unicode-range slices) collapse into one
// cache invalidation instead of causing repeated layout thrashing.
const fontsRevision = ref(0);
if (typeof document !== "undefined") {
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
    if (e.fontfaces.some((f) => (ALLOWED_FONTS as readonly string[]).includes(f.family))) bumpRevision();
  }) as EventListener);
}

// --- Canvas text measurement (no DOM reflow) ---
let canvasCtx: CanvasRenderingContext2D | null = null;
let canvasFont = "";

function ensureCanvas(font: string): CanvasRenderingContext2D {
  if (!canvasCtx) canvasCtx = document.createElement("canvas").getContext("2d")!;
  if (canvasFont !== font) {
    canvasCtx.font = font;
    canvasFont = font;
  }
  return canvasCtx;
}

// --- Zone geometry (resolved from CSS vars) ---
interface ZoneConfig {
  columnWidth: number;
  maxLines: number;
  font: string;
}

interface LayoutConfig {
  meta: ZoneConfig;
  full: ZoneConfig;
  cont: ZoneConfig;
}

let layoutConfig: LayoutConfig | null = null;

function ensureConfig(): LayoutConfig {
  if (layoutConfig) return layoutConfig;

  const rootStyle = getComputedStyle(document.documentElement);
  const remPx = parseFloat(rootStyle.fontSize);
  const mmPx = 96 / 25.4;
  const lineHeight = 1.65;

  const pageWidth = parseFloat(rootStyle.getPropertyValue("--page-width")) * mmPx;
  const pageHeight = parseFloat(rootStyle.getPropertyValue("--page-height")) * mmPx;
  const metaRatio = parseFloat(rootStyle.getPropertyValue("--meta-ratio"));
  const insetX = parseFloat(rootStyle.getPropertyValue("--page-inset-x")) * remPx;
  const insetY = parseFloat(rootStyle.getPropertyValue("--page-inset-y")) * remPx;
  const typeXs = parseFloat(rootStyle.getPropertyValue("--type-xs")) * remPx;
  const typeSm = parseFloat(rootStyle.getPropertyValue("--type-sm")) * remPx;
  const fontBody = rootStyle.getPropertyValue("--font-album-body").trim();

  // Meta zone: single column in the meta panel sidebar.
  // Empirical 21rem accounts for silhouette, name-block, stats, and progress.
  const metaColWidth = pageWidth * metaRatio - insetX - insetY;
  const metaMaxLines = Math.floor((pageHeight - 21 * remPx) / (typeXs * lineHeight));

  // Full/continuation zones: 2-column layout from .text-body-columns (App.vue).
  // Column gap = insetY. Padding = insetY top/bottom, insetX left/right, box-sizing: border-box.
  const colWidth = (pageWidth - 2 * insetX - insetY) / 2;
  // Full zone: below compact meta header (empirical 11rem) with top+bottom padding.
  const fullMaxLines = 2 * Math.floor((pageHeight - 11 * remPx - 2 * insetY) / (typeSm * lineHeight));
  // Continuation zone: full page height with top+bottom padding.
  const contMaxLines = 2 * Math.floor((pageHeight - 2 * insetY) / (typeSm * lineHeight));

  layoutConfig = {
    meta: { columnWidth: metaColWidth, maxLines: metaMaxLines, font: `${typeXs}px ${fontBody}` },
    full: { columnWidth: colWidth, maxLines: fullMaxLines, font: `${typeSm}px ${fontBody}` },
    cont: { columnWidth: colWidth, maxLines: contMaxLines, font: `${typeSm}px ${fontBody}` },
  };
  return layoutConfig;
}

// --- Knuth-Plass line breaking via tex-linebreak ---

function breakParagraph(para: string, columnWidth: number, measure: (w: string) => number): JustifiedLine[] {
  const items = layoutItemsFromString(para, measure);
  const breakpoints = breakLines(items, columnWidth, { maxAdjustmentRatio: null });
  const positions = positionItems(items, columnWidth, breakpoints, { includeGlue: true });
  const lineCount = breakpoints.length - 1;
  const normalSpaceWidth = measure(" ");

  const result: JustifiedLine[] = [];
  let posIdx = 0;

  for (let lineNum = 0; lineNum < lineCount; lineNum++) {
    const words: string[] = [];
    let glueWidth = normalSpaceWidth;

    while (posIdx < positions.length && positions[posIdx]!.line === lineNum) {
      const pos = positions[posIdx]!;
      const item = items[pos.item]!;
      if (item.type === "box") words.push(item.text);
      else if (item.type === "glue") glueWidth = pos.width;
      posIdx++;
    }

    const isLast = lineNum === lineCount - 1;
    result.push({
      text: words.join(" "),
      wordSpacing: isLast || words.length <= 1 ? 0 : glueWidth - normalSpaceWidth,
    });
  }

  return result;
}

function breakText(text: string, columnWidth: number, font: string): JustifiedLine[] {
  const ctx = ensureCanvas(font);
  const measure = (w: string) => ctx.measureText(w).width;
  const lines: JustifiedLine[] = [];

  for (const para of text.split("\n")) {
    if (!para) {
      lines.push({ text: "", wordSpacing: 0 });
      continue;
    }
    lines.push(...breakParagraph(para, columnWidth, measure));
  }

  return lines;
}

// --- Character-count estimate (fallback while fonts load, ~50-100ms) ---
// Only classifies type — no text splitting or line data until fonts are ready.
const EST_CHARS_PER_LINE = 65;
const EST_SHORT = 1200;
const EST_PAGE = 3600;

function estimateType(text: string): DescriptionType {
  if (!text) return "short";
  let chars = 0;
  for (const para of text.split("\n")) {
    chars += para ? Math.ceil(para.length / EST_CHARS_PER_LINE) * EST_CHARS_PER_LINE : EST_CHARS_PER_LINE;
  }
  if (chars <= EST_SHORT) return "short";
  if (chars <= EST_PAGE) return "long";
  return "extra-long";
}

// --- Public API ---

export function measureDescription(text: string): TextLayout {
  if (fontsRevision.value === 0) return { type: estimateType(text), mainLines: null, continuationLines: [] };

  const hit = cache.get(text);
  if (hit) return hit;

  const config = ensureConfig();

  // Short: fits in meta panel sidebar (single column, smaller font)
  const metaLines = breakText(text, config.meta.columnWidth, config.meta.font);
  if (metaLines.length <= config.meta.maxLines)
    return cached(text, { type: "short", mainLines: metaLines, continuationLines: [] });

  // Long: fits in full-width 2-column area below compact meta header
  const fullLines = breakText(text, config.full.columnWidth, config.full.font);
  if (fullLines.length <= config.full.maxLines)
    return cached(text, { type: "long", mainLines: fullLines, continuationLines: [] });

  // Extra-long: split across main page + continuation pages
  const mainLines = fullLines.slice(0, config.full.maxLines);
  let remaining = fullLines.slice(config.full.maxLines);
  const continuationLines: JustifiedLine[][] = [];
  while (remaining.length > 0) {
    continuationLines.push(remaining.slice(0, config.cont.maxLines));
    remaining = remaining.slice(config.cont.maxLines);
  }

  return cached(text, { type: "extra-long", mainLines, continuationLines });
}

export function useTextMeasure(description: Ref<string>): ComputedRef<TextLayout> {
  return computed(() => measureDescription(description.value));
}
