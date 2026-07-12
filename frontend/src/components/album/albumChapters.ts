import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import { inDateRange, isoDate } from "@/utils/date";

export function stepsForChapter(
  steps: Step[],
  chapter: AlbumChapter | null | undefined,
): Step[] {
  if (!chapter) return steps;
  const wanted = new Set(chapter.step_ids);
  return steps.filter((step) => wanted.has(step.id));
}

export type MapRangeEntry = {
  rangeIdx: number;
  dateRange: DateRange;
  steps: Step[];
};

export function mapRangeEntriesForSteps(
  ranges: DateRange[],
  steps: Step[],
): MapRangeEntry[] {
  return ranges
    .map((dateRange, rangeIdx) => ({
      rangeIdx,
      dateRange,
      steps: steps.filter((step) => inDateRange(isoDate(step.datetime), dateRange)),
    }))
    .filter((entry) => entry.steps.length > 0);
}

export function mapRangesForSteps(
  ranges: DateRange[],
  steps: Step[],
): DateRange[] {
  return mapRangeEntriesForSteps(ranges, steps).map((entry) => entry.dateRange);
}
