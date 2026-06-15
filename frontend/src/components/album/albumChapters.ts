import type { AlbumChapter, DateRange, StepRead as Step } from "@/client";
import { inDateRange, isoDate } from "@/utils/date";

export type StepOption = {
  label: string;
  value: number;
  disable: boolean;
};

export function stepsForChapter(
  steps: Step[],
  chapter: AlbumChapter | null | undefined,
): Step[] {
  if (!chapter) return steps;
  const wanted = new Set(chapter.step_ids);
  return steps.filter((step) => wanted.has(step.id));
}

export function unassignedSteps(
  steps: Step[],
  chapters: readonly AlbumChapter[],
): Step[] {
  const assigned = new Set(chapters.flatMap((chapter) => chapter.step_ids));
  return steps.filter((step) => !assigned.has(step.id));
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

function assignedToOtherChapters(
  chapters: readonly AlbumChapter[],
  chapter: AlbumChapter,
): Set<number> {
  return new Set(
    chapters
      .filter((other) => other.id !== chapter.id)
      .flatMap((other) => other.step_ids)
      .filter((id): id is number => id != null),
  );
}

export function stepOptionsForChapter(
  steps: Step[],
  chapters: readonly AlbumChapter[],
  chapter: AlbumChapter,
): StepOption[] {
  const unavailable = assignedToOtherChapters(chapters, chapter);
  return steps.map((step) => ({
    label: step.name,
    value: step.id,
    disable: unavailable.has(step.id),
  }));
}

export function applyStepRange(
  steps: Step[],
  chapters: readonly AlbumChapter[],
  chapter: AlbumChapter,
  fromStepId: number,
  toStepId: number,
): number[] {
  const fromIndex = steps.findIndex((step) => step.id === fromStepId);
  const toIndex = steps.findIndex((step) => step.id === toStepId);
  if (fromIndex < 0 || toIndex < 0) return [];

  const start = Math.min(fromIndex, toIndex);
  const end = Math.max(fromIndex, toIndex);
  const unavailable = assignedToOtherChapters(chapters, chapter);
  return steps
    .slice(start, end + 1)
    .map((step) => step.id)
    .filter((id) => !unavailable.has(id));
}
