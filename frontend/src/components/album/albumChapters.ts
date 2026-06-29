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

export function mapRangesForSteps(
  ranges: DateRange[],
  steps: Step[],
): DateRange[] {
  const stepDates = new Set(steps.map((step) => isoDate(step.datetime)));
  return ranges.filter((range) =>
    [...stepDates].some((date) => inDateRange(date, range)),
  );
}
