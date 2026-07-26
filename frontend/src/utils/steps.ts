import type { StepRead as Step } from "@/client";

export type StepIndex = {
  byId: Map<number, Step>;
  positionById: Map<number, number>;
};

export function indexSteps(steps: readonly Step[]): StepIndex {
  const byId = new Map<number, Step>();
  const positionById = new Map<number, number>();
  steps.forEach((step, position) => {
    byId.set(step.id, step);
    positionById.set(step.id, position);
  });
  return { byId, positionById };
}
