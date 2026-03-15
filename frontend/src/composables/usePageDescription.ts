import { computed, type Ref } from "vue";

/**
 * Must match backend builder.py _LONG_DESCRIPTION_THRESHOLD / _CHARS_PER_LINE so both
 * agree on whether the cover photo appears on the main page vs. in photo pages.
 * Derived from StepMainPage panel: ~502px wide, 0.9rem/1.5 line-height ≈ 22 lines × 65 chars.
 */
const SHORT_THRESHOLD = 1200;

/**
 * Full-page two-column layout fits ~60 lines × 65 chars ≈ 3900.
 * Conservative estimate for the long threshold.
 */
export const PAGE_CHARS = 3600;

const CHARS_PER_LINE = 65;

export function visualLength(text: string): number {
  if (!text) return 0;
  let lines = 0;
  for (const para of text.split("\n")) {
    lines += para ? Math.ceil(para.length / CHARS_PER_LINE) : 1;
  }
  return lines * CHARS_PER_LINE;
}

function splitAtParagraph(text: string, maxChars: number): [string, string] {
  const paras = text.split("\n");
  let consumed = 0;
  let splitIdx = 0;

  for (let i = 0; i < paras.length; i++) {
    const paraLen = paras[i]!.length || CHARS_PER_LINE;
    if (consumed + paraLen > maxChars && i > 0) break;
    consumed += paraLen;
    splitIdx = i + 1;
  }

  if (splitIdx === 0) splitIdx = 1;
  return [paras.slice(0, splitIdx).join("\n"), paras.slice(splitIdx).join("\n")];
}

export type DescriptionType = "short" | "long" | "extra-long";

export function usePageDescription(description: Ref<string>) {
  return computed(() => {
    const text = description.value;
    const vl = visualLength(text);

    if (vl <= SHORT_THRESHOLD) {
      return {
        type: "short" as DescriptionType,
        mainPageText: text,
        continuationTexts: [] as string[],
      };
    }

    if (vl <= PAGE_CHARS) {
      return {
        type: "long" as DescriptionType,
        mainPageText: text,
        continuationTexts: [] as string[],
      };
    }

    const continuationTexts: string[] = [];
    const [mainText, initialRemainder] = splitAtParagraph(text, PAGE_CHARS);
    let remainder = initialRemainder;

    while (remainder.trim()) {
      const [chunk, rest] = splitAtParagraph(remainder, PAGE_CHARS);
      continuationTexts.push(chunk);
      remainder = rest;
    }

    return {
      type: "extra-long" as DescriptionType,
      mainPageText: mainText,
      continuationTexts,
    };
  });
}
