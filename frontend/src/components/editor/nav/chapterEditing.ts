import type { AlbumChapter, StepRead as Step } from "@/client";

function cloneChapter(chapter: AlbumChapter): AlbumChapter {
  return {
    ...chapter,
    step_ids: [...(chapter.step_ids ?? [])],
  };
}

function nextChapterId(chapters: AlbumChapter[]): string {
  const used = new Set(chapters.map((chapter) => chapter.id));
  for (let index = chapters.length + 1; ; index += 1) {
    const candidate = `chapter-${index}`;
    if (!used.has(candidate)) return candidate;
  }
}

function coverFromSteps(steps: Step[], fallback: string): string {
  return steps.find((step) => step.cover)?.cover ?? fallback;
}

export function splitChapter(
  chapters: AlbumChapter[],
  steps: Step[],
  chapterId: string,
): AlbumChapter[] {
  const index = chapters.findIndex((chapter) => chapter.id === chapterId);
  if (index < 0) return chapters;

  const source = chapters[index];
  const sourceStepIds = source.step_ids ?? [];
  if (sourceStepIds.length < 2) return chapters;

  const splitAt = Math.ceil(sourceStepIds.length / 2);
  const firstStepIds = sourceStepIds.slice(0, splitAt);
  const nextStepIds = sourceStepIds.slice(splitAt);
  const stepsById = new Map(steps.map((step) => [step.id, step]));
  const nextSteps = nextStepIds
    .map((stepId) => stepsById.get(stepId))
    .filter((step): step is Step => Boolean(step));
  const fallbackCover = source.front_cover_photo || source.back_cover_photo || "";
  const cover = coverFromSteps(nextSteps, fallbackCover);
  const nextChapter: AlbumChapter = {
    id: nextChapterId(chapters),
    title: "",
    subtitle: "",
    step_ids: nextStepIds,
    front_cover_photo: cover,
    back_cover_photo: cover,
  };

  const result = chapters.map(cloneChapter);
  result[index] = { ...result[index], step_ids: firstStepIds };
  result.splice(index + 1, 0, nextChapter);
  return result;
}

export function deleteChapter(
  chapters: AlbumChapter[],
  chapterId: string,
): AlbumChapter[] {
  if (chapters.length <= 1) return chapters;
  const index = chapters.findIndex((chapter) => chapter.id === chapterId);
  if (index < 0) return chapters;

  const result = chapters.map(cloneChapter);
  const removed = result[index];
  if (index > 0) {
    result[index - 1] = {
      ...result[index - 1],
      step_ids: [
        ...(result[index - 1].step_ids ?? []),
        ...(removed.step_ids ?? []),
      ],
    };
  } else {
    result[index + 1] = {
      ...result[index + 1],
      step_ids: [
        ...(removed.step_ids ?? []),
        ...(result[index + 1].step_ids ?? []),
      ],
    };
  }
  result.splice(index, 1);
  return result;
}

export function adjustChapterBoundary(
  chapters: AlbumChapter[],
  leftChapterId: string,
  rightChapterId: string,
  firstRightStepId: number,
): AlbumChapter[] {
  const leftIndex = chapters.findIndex((chapter) => chapter.id === leftChapterId);
  const rightIndex = chapters.findIndex(
    (chapter) => chapter.id === rightChapterId,
  );
  if (leftIndex < 0 || rightIndex !== leftIndex + 1) return chapters;

  const left = chapters[leftIndex];
  const right = chapters[rightIndex];
  const combined = [...(left.step_ids ?? []), ...(right.step_ids ?? [])];
  const splitAt = combined.indexOf(firstRightStepId);
  if (splitAt <= 0 || splitAt >= combined.length) return chapters;

  const result = chapters.map(cloneChapter);
  result[leftIndex] = { ...result[leftIndex], step_ids: combined.slice(0, splitAt) };
  result[rightIndex] = {
    ...result[rightIndex],
    step_ids: combined.slice(splitAt),
  };
  return result;
}

export function chapterCanSplit(chapter: AlbumChapter): boolean {
  return (chapter.step_ids?.length ?? 0) >= 2;
}
