import type { AlbumChapter, StepRead as Step } from "@/client";
import type { ChapterStartOption } from "./types";

type ChapterBoundaryOptionsInput = {
  left: AlbumChapter;
  right: AlbumChapter;
  steps: Step[];
  countryName: (code: string, detail: string) => string;
};

function stepLabel(step: Step | undefined, stepId: number): string {
  return step?.name || step?.location.name || String(stepId);
}

export function chapterBoundaryOptions({
  left,
  right,
  steps,
  countryName,
}: ChapterBoundaryOptionsInput): ChapterStartOption[] {
  const stepsById = new Map(steps.map((step) => [step.id, step]));
  const combined = [...(left.step_ids ?? []), ...(right.step_ids ?? [])];
  return combined.slice(1).map((stepId) => {
    const step = stepsById.get(stepId);
    const countryCode = step?.location.country_code ?? "";
    return {
      label: stepLabel(step, stepId),
      value: stepId,
      countryCode,
      countryLabel: step ? countryName(countryCode, step.location.detail) : String(stepId),
    };
  });
}
