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

// Positioning for all hidden measurement containers — text formatting
// comes from the .text-body-columns CSS class (App.vue) or inline styles.
const MEASURE_STYLE = [
  "position:fixed",
  "visibility:hidden",
  "pointer-events:none",
  "z-index:-1",
  "font-family:Inter,sans-serif",
].join(";");

function createContainer(extraStyle: string, className?: string): HTMLDivElement {
  const el = document.createElement("div");
  el.style.cssText = MEASURE_STYLE + ";" + extraStyle;
  if (className) el.className = className;
  document.body.appendChild(el);
  return el;
}

function ensureContainers() {
  if (metaMeasure) return;

  // Matches StepMetaPanel .description — flex:1 area in the meta-ratio-wide sidebar.
  // Empirical height (21rem) accounts for silhouette, name-block, stats, and progress.
  metaMeasure = createContainer(
    [
      "white-space:pre-wrap",
      "text-align:justify",
      "overflow:hidden",
      "box-sizing:border-box",
      "width:calc(var(--page-width) * var(--meta-ratio) - var(--page-inset-x) - var(--page-inset-y))",
      "height:calc(var(--page-height) - 21rem)",
      "font-size:var(--type-xs)",
      "line-height:1.65",
    ].join(";"),
  );

  // Matches StepMainPage .description-full — full-width 2-column layout below compact meta.
  // Empirical height (11rem) accounts for the compact meta header grid.
  // Text formatting from .text-body-columns class (App.vue) — single source of truth.
  fullMeasure = createContainer(
    [
      "width:var(--page-width)",
      "height:calc(var(--page-height) - 11rem)",
    ].join(";"),
    "text-body-columns",
  );

  // Matches StepTextPage .text-page-body — continuation text pages (same 2-column layout).
  // Text formatting from .text-body-columns class (App.vue) — single source of truth.
  contMeasure = createContainer(
    [
      "width:var(--page-width)",
      "height:var(--page-height)",
    ].join(";"),
    "text-body-columns",
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

/** Check if content overflows the container (vertical or horizontal for multi-column). */
function overflows(container: HTMLDivElement): boolean {
  return (
    container.scrollHeight > container.clientHeight ||
    container.scrollWidth > container.clientWidth
  );
}

function fits(container: HTMLDivElement, text: string): boolean {
  container.textContent = text;
  return !overflows(container);
}

/** Binary-search split within a single paragraph by word boundaries. */
function splitByWords(
  container: HTMLDivElement,
  paragraph: string,
): [string, string] {
  const words = paragraph.split(/(?<=\s)/);
  if (words.length <= 1) return [paragraph, ""];

  // Pre-build joined prefixes so each binary search probe is O(1) lookup
  const prefixes: string[] = new Array(words.length);
  prefixes[0] = words[0]!;
  for (let i = 1; i < words.length; i++) {
    prefixes[i] = prefixes[i - 1]! + words[i]!;
  }

  let lo = 0;
  let hi = words.length - 1;
  let splitAt = 1; // take at least one word

  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    container.textContent = prefixes[mid]!;
    if (!overflows(container)) {
      splitAt = mid + 1;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  if (splitAt >= words.length) return [paragraph, ""];
  return [
    prefixes[splitAt - 1]!.trimEnd(),
    words.slice(splitAt).join(""),
  ];
}

function splitToFit(
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
    if (!overflows(container)) {
      mainEnd = mid + 1;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  // If even the first paragraph overflows, split it by words
  if (mainEnd === 0 && paras.length > 0) {
    const [head, tail] = splitByWords(container, paras[0]!);
    const rest = paras.slice(1).join("\n");
    return [head, tail + (rest ? "\n" + rest : "")];
  }

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

  const [mainPageText, remainder] = splitToFit(fullMeasure!, text);
  const continuationTexts: string[] = [];
  let remaining = remainder;

  while (remaining.trim()) {
    const [chunk, rest] = splitToFit(contMeasure!, remaining);
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
  cover: string | null | undefined,
  isShort: boolean,
): IndexedPage[] {
  if (!isShort || !cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({ originalIdx: i, page: page.filter((p) => p !== cover) }))
    .filter(({ page }) => page.length > 0);
}
