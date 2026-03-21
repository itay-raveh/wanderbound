import type { DateRange, Segment, Step } from "@/client";
import { measureDescription } from "@/composables/useTextMeasure";
import { inDateRange, isoDate } from "@/utils/date";

export interface IndexedPage {
  originalIdx: number;
  page: string[];
}

/** Filter out the cover photo from pages when it's already shown on the main page (short description). */
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

export type Section =
  | { type: "map"; steps: Step[]; segments: Segment[]; rangeIdx: number; dateRange: DateRange }
  | { type: "hike"; steps: Step[]; segments: Segment[]; hikeSegment: Segment; rangeIdx: number; dateRange: DateRange }
  | { type: "step"; step: Step };

export function segmentsOverlapping(segs: Segment[], tStart: number, tEnd: number): Segment[] {
  return segs.filter((seg) => seg.start_time <= tEnd && seg.end_time >= tStart);
}

export function sectionKey(section: Section): string {
  switch (section.type) {
    case "step": return `step-${section.step.id}`;
    case "map": return `map-${section.dateRange[0]}-${section.dateRange[1]}`;
    case "hike": return `hike-${section.dateRange[0]}-${section.dateRange[1]}`;
  }
}

export function sectionPageCount(section: Section): number {
  if (section.type === "map" || section.type === "hike") return 1;
  const step = section.step;
  const layout = measureDescription(step.description || "");
  const pages = filterCoverFromPages(step.pages, step.cover, layout.type === "short");
  return 1 + pages.length + layout.continuationTexts.length;
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
  allSegments: Segment[],
  mapRanges: DateRange[],
): Section[] {
  type MapEntry = {
    rangeIdx: number;
    dateRange: DateRange;
    steps: Step[];
    segments: Segment[];
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
  const mapInsertionPoints = new Map<number, MapEntry[]>();
  for (const entry of mapEntries) {
    if (entry.steps.length === 0) continue;
    const firstId = entry.steps[0]!.id;
    if (!mapInsertionPoints.has(firstId)) {
      mapInsertionPoints.set(firstId, []);
    }
    mapInsertionPoints.get(firstId)!.push(entry);
  }

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
