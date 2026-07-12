import type {
  AlbumChapter,
  AlbumMeta,
  AlbumMedia,
  DateRange,
  SegmentOutline,
  StepRead as Step,
} from "@/client";
import { inDateRange, isoDate } from "@/utils/date";
import { planStepPages } from "./stepPages";

/** Keys for fixed album pages that precede the data-driven sections. Validated against the API schema. */
export const HEADER_KEYS = [
  "cover-front",
  "cover-back",
  "overview",
  "full-map",
] as const satisfies readonly NonNullable<
  AlbumMeta["hidden_headers"]
>[number][];

export type HeaderKey = (typeof HEADER_KEYS)[number];

export function chapterHeaderSectionKey(
  chapterId: string,
  headerKey: HeaderKey,
): string {
  return `chapter-${chapterId}-${headerKey}`;
}

export function parseChapterHeaderSectionKey(
  key: string | null | undefined,
): { chapterId: string; headerKey: HeaderKey } | null {
  if (!key?.startsWith("chapter-")) return null;
  const headerKey = HEADER_KEYS.find((candidate) =>
    key.endsWith(`-${candidate}`),
  );
  if (!headerKey) return null;
  const chapterId = key.slice(
    "chapter-".length,
    key.length - headerKey.length - 1,
  );
  return chapterId ? { chapterId, headerKey } : null;
}

/** Return only the header keys not present in the hidden list. */
export function visibleHeaderKeys(
  hiddenHeaders: readonly HeaderKey[],
): HeaderKey[] {
  if (!hiddenHeaders.length) return [...HEADER_KEYS];
  const hidden = new Set(hiddenHeaders);
  return HEADER_KEYS.filter((k) => !hidden.has(k));
}

export type Section =
  | {
      type: "map";
      chapterId?: string;
      steps: Step[];
      segments: SegmentOutline[];
      rangeIdx: number;
      dateRange: DateRange;
    }
  | {
      type: "hike";
      chapterId?: string;
      steps: Step[];
      segments: SegmentOutline[];
      hikeSegment: SegmentOutline;
      rangeIdx: number;
      dateRange: DateRange;
    }
  | { type: "step"; step: Step };

export function segmentsOverlapping(
  segs: SegmentOutline[],
  tStart: number,
  tEnd: number,
): SegmentOutline[] {
  return segs.filter((seg) => seg.start_time <= tEnd && seg.end_time >= tStart);
}

export type MapRangeEntry = {
  rangeIdx: number;
  dateRange: DateRange;
  steps: Step[];
};

export function mapRangeEntriesForSteps(
  steps: Step[],
  mapRanges: DateRange[],
): MapRangeEntry[] {
  return mapRanges
    .map((dateRange, rangeIdx) => ({
      rangeIdx,
      dateRange,
      steps: steps.filter((step) => inDateRange(isoDate(step.datetime), dateRange)),
    }))
    .filter((entry) => entry.steps.length > 0);
}

export function rangeSectionKey(
  type: "map" | "hike",
  dateRange: DateRange,
  chapter?: AlbumChapter | string,
): string {
  const chapterId = typeof chapter === "string" ? chapter : chapter?.id;
  const suffix = `${type}-${dateRange[0]}-${dateRange[1]}`;
  return chapterId ? `chapter-${chapterId}-${suffix}` : suffix;
}

export function sectionKey(section: Section): string {
  switch (section.type) {
    case "step":
      return `step-${section.step.id}`;
    case "map":
    case "hike":
      return rangeSectionKey(section.type, section.dateRange, section.chapterId);
  }
}

/** Return the nav ID for a section at the given index (header-offset already removed). */
export function activeSectionId(
  sections: readonly Section[],
  sectionIdx: number,
): number | string | undefined {
  const sec = sections[sectionIdx];
  if (!sec) return undefined;
  return sec.type === "step" ? sec.step.id : sectionKey(sec);
}

export function stepPageCount(
  step: Step,
  mediaByName: ReadonlyMap<string, AlbumMedia> = new Map(),
): number {
  const plan = planStepPages(step, mediaByName);
  return plan.editorPagePhotoIds.length;
}

export function sectionPageCount(
  section: Section,
  mediaByName?: ReadonlyMap<string, AlbumMedia>,
): number {
  if (section.type === "map" || section.type === "hike") return 1;
  const step = section.step;
  return stepPageCount(step, mediaByName);
}

/** Group map ranges by the ID of their first overlapping step. */
export function mapInsertionsByStep<T extends { dateRange: DateRange }>(
  steps: Step[],
  entries: T[],
): Map<number, T[]> {
  const result = new Map<number, T[]>();
  for (const entry of entries) {
    const first = steps.find((s) =>
      inDateRange(isoDate(s.datetime), entry.dateRange),
    );
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
  chapter?: AlbumChapter,
): Section[] {
  const mapEntries = mapRangeEntriesForSteps(allSteps, mapRanges).map((entry) => {
    const rangeSteps = entry.steps;
    const rangeStart = rangeSteps[0]?.timestamp;
    const rangeEnd = rangeSteps[rangeSteps.length - 1]?.timestamp;
    const rangeSegments =
      rangeStart == null || rangeEnd == null
        ? []
        : segmentsOverlapping(allSegments, rangeStart, rangeEnd);
    return {
      ...entry,
      steps: rangeSteps,
      segments: rangeSegments,
    };
  });

  const result: Section[] = [];
  const mapInsertionPoints = mapInsertionsByStep(allSteps, mapEntries);

  for (const step of allSteps) {
    const maps = mapInsertionPoints.get(step.id);
    if (maps) {
      for (const m of maps) {
        const hikeSegment = m.segments.find((s) => s.kind === "hike");
        const hasTransport = m.segments.some(
          (s) => s.kind === "driving" || s.kind === "flight",
        );
        if (hikeSegment && !hasTransport) {
          result.push({
            type: "hike" as const,
            ...m,
            chapterId: chapter?.id,
            hikeSegment,
          });
        } else {
          result.push({ type: "map" as const, ...m, chapterId: chapter?.id });
        }
      }
    }
    result.push({ type: "step", step });
  }

  return result;
}
