import type { AlbumChapter, StepRead as Step } from "@/client";
import { indexSteps } from "@/utils/steps";
import type { StepSelectOption } from "./types";

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
}: ChapterBoundaryOptionsInput): StepSelectOption[] {
  const { byId } = indexSteps(steps);
  const combined = [...(left.step_ids ?? []), ...(right.step_ids ?? [])];
  return combined.slice(1).map((stepId) => {
    const step = byId.get(stepId);
    const countryCode = step?.location.country_code ?? "";
    return {
      label: stepLabel(step, stepId),
      value: stepId,
      countryCode,
      countryLabel: step ? countryName(countryCode, step.location.detail) : String(stepId),
    };
  });
}
