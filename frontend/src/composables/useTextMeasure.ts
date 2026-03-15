import { computed, ref, type ComputedRef, type Ref } from "vue";

export type DescriptionType = "short" | "long" | "extra-long";

export interface TextLayout {
  type: DescriptionType;
  mainPageText: string;
  continuationTexts: string[];
}

// --- Measurement cache (cleared when fonts finish loading) ---
const cache = new Map<string, TextLayout>();

function cached(text: string, layout: TextLayout): TextLayout {
  cache.set(text, layout);
  return layout;
}

// --- Font readiness tracking (reactive — triggers recomputation in computed contexts) ---
const fontsLoaded = ref(false);
if (typeof document !== "undefined") {
  void document.fonts.ready.then(() => {
    fontsLoaded.value = true;
    cache.clear();
  });
}

// --- Hidden DOM containers (created once on first use) ---
let metaMeasure: HTMLDivElement | null = null;
let fullMeasure: HTMLDivElement | null = null;
let contMeasure: HTMLDivElement | null = null;

const COMMON_STYLE = [
  "position:fixed",
  "visibility:hidden",
  "pointer-events:none",
  "z-index:-1",
  "white-space:pre-wrap",
  "text-align:justify",
  "font-family:Inter,sans-serif",
  "box-sizing:border-box",
  "overflow:hidden",
].join(";");

function createContainer(extraStyle: string): HTMLDivElement {
  const el = document.createElement("div");
  el.style.cssText = COMMON_STYLE + ";" + extraStyle;
  document.body.appendChild(el);
  return el;
}

function ensureContainers() {
  if (metaMeasure) return;

  // Matches StepMetaPanel .description — flex:1 area in the 42%-wide sidebar
  metaMeasure = createContainer(
    [
      "width:calc(var(--page-width) * 0.42 - 5.5rem)",
      "height:calc(var(--page-height) - 21rem)",
      "font-size:0.75rem",
      "line-height:1.65",
    ].join(";"),
  );

  // Matches StepMainPage .description-full — full-width 2-column layout below compact meta
  fullMeasure = createContainer(
    [
      "width:var(--page-width)",
      "height:calc(var(--page-height) - 11rem)",
      "padding:2.5rem 3rem",
      "font-size:0.9rem",
      "line-height:1.65",
      "column-count:2",
      "column-gap:2.5rem",
    ].join(";"),
  );

  // Matches StepTextPage .text-page-body — continuation text pages
  contMeasure = createContainer(
    [
      "width:var(--page-width)",
      "height:calc(var(--page-height) - 4rem)",
      "padding:0 4rem 3rem",
      "font-size:1rem",
      "line-height:1.6",
      "column-width:30rem",
      "column-fill:auto",
      "column-gap:3rem",
    ].join(";"),
  );
}

// --- Character-count estimate (fallback while fonts load, ~50-100ms) ---
const EST_CHARS_PER_LINE = 65;
const EST_SHORT = 1200;
const EST_PAGE = 3600;

function estimateVisualLength(text: string): number {
  if (!text) return 0;
  let lines = 0;
  for (const para of text.split("\n")) {
    lines += para ? Math.ceil(para.length / EST_CHARS_PER_LINE) : 1;
  }
  return lines * EST_CHARS_PER_LINE;
}

function estimateSplit(text: string, maxChars: number): [string, string] {
  const paras = text.split("\n");
  let consumed = 0;
  let splitIdx = 0;
  for (let i = 0; i < paras.length; i++) {
    const paraLen = paras[i]!.length || EST_CHARS_PER_LINE;
    if (consumed + paraLen > maxChars && i > 0) break;
    consumed += paraLen;
    splitIdx = i + 1;
  }
  if (splitIdx === 0) splitIdx = 1;
  return [paras.slice(0, splitIdx).join("\n"), paras.slice(splitIdx).join("\n")];
}

function estimateLayout(text: string): TextLayout {
  const vl = estimateVisualLength(text);
  if (vl <= EST_SHORT) return { type: "short", mainPageText: text, continuationTexts: [] };
  if (vl <= EST_PAGE) return { type: "long", mainPageText: text, continuationTexts: [] };

  const [mainText, initialRemainder] = estimateSplit(text, EST_PAGE);
  const continuationTexts: string[] = [];
  let remainder = initialRemainder;
  while (remainder.trim()) {
    const [chunk, rest] = estimateSplit(remainder, EST_PAGE);
    continuationTexts.push(chunk);
    remainder = rest;
  }
  return { type: "extra-long", mainPageText: mainText, continuationTexts };
}

// --- DOM measurement helpers ---
function fits(container: HTMLDivElement, text: string): boolean {
  container.textContent = text;
  return container.scrollHeight <= container.clientHeight;
}

function splitByParagraphs(
  container: HTMLDivElement,
  text: string,
): [string, string] {
  const paras = text.split("\n");

  // Pre-build joined prefixes so each binary search probe is O(1) lookup
  const prefixes: string[] = new Array(paras.length);
  for (let i = 0; i < paras.length; i++) {
    prefixes[i] = i === 0 ? paras[0]! : prefixes[i - 1]! + "\n" + paras[i]!;
  }

  let lo = 0;
  let hi = paras.length - 1;
  let mainEnd = 0;

  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    container.textContent = prefixes[mid]!;
    if (container.scrollHeight <= container.clientHeight) {
      mainEnd = mid + 1;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  if (mainEnd === 0 && paras.length > 0) mainEnd = 1;
  if (mainEnd >= paras.length) return [text, ""];
  return [prefixes[mainEnd - 1]!, paras.slice(mainEnd).join("\n")];
}

// --- Public API ---

export function measureDescription(text: string): TextLayout {
  if (!fontsLoaded.value) return estimateLayout(text);

  const hit = cache.get(text);
  if (hit) return hit;

  ensureContainers();

  if (fits(metaMeasure!, text))
    return cached(text, { type: "short", mainPageText: text, continuationTexts: [] });

  if (fits(fullMeasure!, text))
    return cached(text, { type: "long", mainPageText: text, continuationTexts: [] });

  const [mainPageText, remainder] = splitByParagraphs(fullMeasure!, text);
  const continuationTexts: string[] = [];
  let remaining = remainder;

  while (remaining.trim()) {
    const [chunk, rest] = splitByParagraphs(contMeasure!, remaining);
    continuationTexts.push(chunk);
    remaining = rest;
  }

  return cached(text, { type: "extra-long", mainPageText, continuationTexts });
}

export function useTextMeasure(description: Ref<string>): ComputedRef<TextLayout> {
  return computed(() => measureDescription(description.value));
}

export interface IndexedPage {
  originalIdx: number;
  page: string[];
}

export function filterCoverFromPages(
  pages: string[][],
  cover: string | null,
  isShort: boolean,
): IndexedPage[] {
  if (!isShort || !cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({ originalIdx: i, page: page.filter((p) => p !== cover) }))
    .filter(({ page }) => page.length > 0);
}
