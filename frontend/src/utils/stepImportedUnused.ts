import type { StepRead as Step } from "@/client";

export function mergeImportedUnused(
  step: Step,
  names: readonly string[],
): Step {
  const alreadyPlaced = new Set([
    ...step.unused,
    ...step.pages.flat(),
    ...(step.cover ? [step.cover] : []),
  ]);
  const imported = names.filter((name) => !alreadyPlaced.has(name));
  return imported.length
    ? { ...step, unused: [...imported, ...step.unused] }
    : step;
}
