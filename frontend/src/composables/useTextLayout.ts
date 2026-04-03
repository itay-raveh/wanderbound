import { computed, ref, type ComputedRef, type Ref } from "vue";
import { prepareWithSegments, layoutWithLines, clearCache as clearPretextCache } from "@chenglou/pretext";
import { ALLOWED_FONTS } from "@/utils/fonts";

export interface JustifiedLine {
  text: string;
}

interface TextLayout {
  pages: JustifiedLine[][]; // pages[0] = sidebar, pages[1..N] = continuation
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

// Debounced revision counter — bumped when fonts finish loading so reactive
// consumers (useTextLayout computeds) re-run. The loadingdone listener catches
// unicode-range fonts (e.g. Hebrew subsets) that load on demand after initial ready.
const fontsRevision = ref(0);
if (typeof document !== "undefined" && document.fonts && !(globalThis as Record<string, unknown>).__textLayoutFontsInit) {
  (globalThis as Record<string, unknown>).__textLayoutFontsInit = true;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  const bumpRevision = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      fontsRevision.value++;
      cache.clear();
      clearPretextCache();
      layoutConfig = null;
    }, 100);
  };
  void document.fonts.ready.then(bumpRevision);
  document.fonts.addEventListener("loadingdone", ((e: FontFaceSetLoadEvent) => {
    if (e.fontfaces.some((f) => (ALLOWED_FONTS as readonly string[]).includes(f.family))) bumpRevision();
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
  const fontBody = rootStyle.getPropertyValue("--font-album-body").trim();

  // Both sidebar and continuation pages use the same column width and font.
  // Right padding is insetY (not insetX) — matches StepMetaPanel/StepDescriptionPage
  // padding shorthand: `insetY insetY insetY insetX` (vertical value reused as inner gap).
  const columnWidth = pageWidth * metaRatio - insetX - insetY;
  const font = `${typeXs}px ${fontBody}`;
  const lineHeightPx = typeXs * lineHeight;

  // Sidebar: vertical space consumed by StepMetaPanel chrome above/below the
  // description slot. Derivation (values from App.vue design tokens):
  //   top padding (--page-inset-y)        2.5rem
  //   silhouette row (5rem + gap-lg)      6.0rem
  //   name block (~2 lines + gap-lg)      3.0rem
  //   stats bar + progress + bot padding  7.0rem
  //   rounding headroom                   2.5rem
  //                                      ------
  //                                      ~21 rem
  // If StepMetaPanel layout changes, re-derive this constant.
  const META_PANEL_CHROME_REM = 21;
  const sidebarMaxLines = Math.floor((pageHeight - META_PANEL_CHROME_REM * remPx) / lineHeightPx);

  // Continuation pages: full page height with top + bottom padding.
  const continuationMaxLines = Math.floor((pageHeight - 2 * insetY) / lineHeightPx);

  layoutConfig = {
    sidebar: { columnWidth, maxLines: sidebarMaxLines, font, lineHeightPx },
    continuation: { columnWidth, maxLines: continuationMaxLines, font, lineHeightPx },
  };
  return layoutConfig;
}

function breakParagraph(para: string, columnWidth: number, font: string, lineHeightPx: number): JustifiedLine[] {
  const prepared = prepareWithSegments(para, font);
  const { lines } = layoutWithLines(prepared, columnWidth, lineHeightPx);
  return lines.map((line) => ({ text: line.text }));
}

function breakText(text: string, columnWidth: number, font: string, lineHeightPx: number): JustifiedLine[] {
  const lines: JustifiedLine[] = [];

  for (const para of text.split("\n")) {
    if (!para) {
      lines.push({ text: "" });
      continue;
    }
    lines.push(...breakParagraph(para, columnWidth, font, lineHeightPx));
  }

  return lines;
}

export function distributePages(
  allLines: JustifiedLine[],
  sidebarMax: number,
  continuationMax: number,
): JustifiedLine[][] {
  if (allLines.length === 0) return [[]];
  if (!Number.isFinite(sidebarMax) || sidebarMax < 1) sidebarMax = allLines.length;
  if (!Number.isFinite(continuationMax) || continuationMax < 1) continuationMax = allLines.length;

  const pages: JustifiedLine[][] = [allLines.slice(0, sidebarMax)];
  for (let i = sidebarMax; i < allLines.length; i += continuationMax) {
    pages.push(allLines.slice(i, i + continuationMax));
  }
  return pages;
}


export function layoutDescription(text: string): TextLayout {
  if (fontsRevision.value === 0) return { pages: [] };

  const hit = cache.get(text);
  if (hit) return hit;

  const config = ensureConfig();
  const allLines = breakText(text, config.sidebar.columnWidth, config.sidebar.font, config.sidebar.lineHeightPx);
  const pages = distributePages(allLines, config.sidebar.maxLines, config.continuation.maxLines);

  return cached(text, { pages });
}

export function useTextLayout(description: Ref<string>): ComputedRef<TextLayout> {
  return computed(() => layoutDescription(description.value));
}
