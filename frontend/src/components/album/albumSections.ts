import type { Album, DateRange, SegmentOutline, Step } from "@/client";
import { layoutDescription } from "@/composables/useTextLayout";
import { inDateRange, isoDate } from "@/utils/date";

/** Keys for fixed album pages that precede the data-driven sections. Validated against the API schema. */
export const HEADER_KEYS = ["cover-front", "cover-back", "overview", "full-map"] as const satisfies
  readonly NonNullable<Album["hidden_headers"]>[number][];

export type HeaderKey = typeof HEADER_KEYS[number];

/** Return only the header keys not present in the hidden list. */
export function visibleHeaderKeys(hiddenHeaders: readonly HeaderKey[]): HeaderKey[] {
  if (!hiddenHeaders.length) return [...HEADER_KEYS];
  const hidden = new Set(hiddenHeaders);
  return HEADER_KEYS.filter(k => !hidden.has(k));
}

interface IndexedPage {
  originalIdx: number;
  page: string[];
}

/** Filter out the cover photo from photo pages (cover is always shown on the main page). */
export function filterCoverFromPages(
  pages: string[][],
  cover: string | null | undefined,
): IndexedPage[] {
  if (!cover) {
    return pages.map((page, i) => ({ originalIdx: i, page }));
  }
  return pages
    .map((page, i) => ({ originalIdx: i, page: page.filter((p) => p !== cover) }))
    .filter(({ page }) => page.length > 0);
}

export type Section =
  | { type: "map"; steps: Step[]; segments: SegmentOutline[]; rangeIdx: number; dateRange: DateRange }
  | { type: "hike"; steps: Step[]; segments: SegmentOutline[]; hikeSegment: SegmentOutline; rangeIdx: number; dateRange: DateRange }
  | { type: "step"; step: Step };

export function segmentsOverlapping(segs: SegmentOutline[], tStart: number, tEnd: number): SegmentOutline[] {
  return segs.filter((seg) => seg.start_time <= tEnd && seg.end_time >= tStart);
}

export function rangeSectionKey(type: "map" | "hike", dateRange: DateRange): string {
  return `${type}-${dateRange[0]}-${dateRange[1]}`;
}

export function sectionKeyMatchesRange(key: string | null, dr: DateRange): boolean {
  if (!key) return false;
  return key === rangeSectionKey("map", dr) || key === rangeSectionKey("hike", dr);
}

export function sectionKey(section: Section): string {
  switch (section.type) {
    case "step": return `step-${section.step.id}`;
    case "map":
    case "hike": return rangeSectionKey(section.type, section.dateRange);
  }
}

/** Return the nav ID for a section at the given index (header-offset already removed). */
export function activeSectionId(sections: readonly Section[], sectionIdx: number): number | string | undefined {
  const sec = sections[sectionIdx];
  if (!sec) return undefined;
  return sec.type === "step" ? sec.step.id : sectionKey(sec);
}

export function sectionPageCount(section: Section): number {
  if (section.type === "map" || section.type === "hike") return 1;
  const step = section.step;
  const layout = layoutDescription(step.description || "");
  const photoPages = filterCoverFromPages(step.pages, step.cover);
  const continuationPages = Math.max(0, layout.pages.length - 1);
  return 1 + continuationPages + photoPages.length;
}

/** Group map ranges by the ID of their first overlapping step. */
export function mapInsertionsByStep<T extends { dateRange: DateRange }>(
  steps: Step[],
  entries: T[],
): Map<number, T[]> {
  const result = new Map<number, T[]>();
  for (const entry of entries) {
    const first = steps.find((s) => inDateRange(isoDate(s.datetime), entry.dateRange));
    if (!first) continue;
    if (!result.has(first.id)) result.set(first.id, []);
    result.get(first.id)!.push(entry);
  }
  return result;
}

/**
 * Build the ordered list of album sections: maps/hikes interleaved with steps.
 *
 * Each map range is inserted before its first step. A range whose segments
 * contain only a hike (no transport) becomes a "hike" section; otherwise
 * it becomes a "map" section.
 */
export function buildSections(
  allSteps: Step[],
  allSegments: SegmentOutline[],
  mapRanges: DateRange[],
): Section[] {
  type MapEntry = {
    rangeIdx: number;
    dateRange: DateRange;
    steps: Step[];
    segments: SegmentOutline[];
  };
  const mapEntries: MapEntry[] = mapRanges.map((dr, i) => {
    const rangeSteps = allSteps.filter((s) => inDateRange(isoDate(s.datetime), dr));
    const rangeStart = rangeSteps[0]?.timestamp;
    const rangeEnd = rangeSteps[rangeSteps.length - 1]?.timestamp;
    const rangeSegments =
      rangeStart == null || rangeEnd == null
        ? []
        : segmentsOverlapping(allSegments, rangeStart, rangeEnd);
    return { rangeIdx: i, dateRange: dr, steps: rangeSteps, segments: rangeSegments };
  });

  const result: Section[] = [];
  const mapInsertionPoints = mapInsertionsByStep(allSteps, mapEntries);

  for (const step of allSteps) {
    const maps = mapInsertionPoints.get(step.id);
    if (maps) {
      for (const m of maps) {
        const hikeSegment = m.segments.find((s) => s.kind === "hike");
        const hasTransport = m.segments.some((s) => s.kind === "driving" || s.kind === "flight");
        if (hikeSegment && !hasTransport) {
          result.push({ type: "hike" as const, ...m, hikeSegment });
        } else {
          result.push({ type: "map" as const, ...m });
        }
      }
    }
    result.push({ type: "step", step });
  }

  return result;
}
