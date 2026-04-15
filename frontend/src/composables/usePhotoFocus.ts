import type { Step, StepUpdate } from "@/client";
import { ref, type InjectionKey, readonly } from "vue";
import { coverUpdatePayload, unusedUpdatePayload } from "./useStepLayout";

export const STEP_ID_KEY: InjectionKey<number> = Symbol("step-id");

const focusedStepId = ref<number | null>(null);
const focusedPhotoId = ref<string | null>(null);

let getSteps: () => Step[] = () => [];
let mutateFn: ((sid: number, update: Partial<StepUpdate>) => void) | null =
  null;
let scrollToStepFn: ((stepId: number) => void) | null = null;
let scrollRafId = 0;
let awaitingStepTransition = false;

/** Cover is shown on StepMainPage (not focusable) - skip it in navigation. */
function pagedPhotos(step: Step): string[] {
  const all = step.pages.flat();
  return step.cover ? all.filter((p) => p !== step.cover) : all;
}

function getStep(stepId: number): Step | undefined {
  return getSteps().find((s) => s.id === stepId);
}

function advanceFocus(photos: string[], removedIdx: number) {
  if (removedIdx < 0 || photos.length <= 1) {
    focusedStepId.value = null;
    focusedPhotoId.value = null;
    return;
  }
  const focusIdx =
    removedIdx < photos.length - 1 ? removedIdx + 1 : removedIdx - 1;
  focusedPhotoId.value = photos[focusIdx]!;
  scrollFocusedIntoView();
}

function init(config: {
  steps: () => Step[];
  mutate: (sid: number, update: Partial<StepUpdate>) => void;
  scrollToStep: (stepId: number) => void;
}) {
  getSteps = config.steps;
  mutateFn = config.mutate;
  scrollToStepFn = config.scrollToStep;
}

function dispose() {
  cancelAnimationFrame(scrollRafId);
  scrollRafId = 0;
  awaitingStepTransition = false;
  focusedStepId.value = null;
  focusedPhotoId.value = null;
  getSteps = () => [];
  mutateFn = null;
  scrollToStepFn = null;
}

/**
 * Scroll the focused media element into view.
 * After cross-step navigation the target may not be mounted yet
 * (the virtualizer smooth-scrolls, then mounts new items). We poll
 * with requestAnimationFrame for up to ~1s waiting for the element.
 */
function scrollFocusedIntoView() {
  cancelAnimationFrame(scrollRafId);
  const photoId = focusedPhotoId.value;
  if (!photoId) {
    awaitingStepTransition = false;
    return;
  }

  let attempts = 0;
  function tryScroll() {
    const el = document.querySelector<HTMLElement>(".media-item.focused");
    if (el) {
      scrollRafId = 0;
      awaitingStepTransition = false;
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    if (++attempts < 60) {
      scrollRafId = requestAnimationFrame(tryScroll);
    } else {
      scrollRafId = 0;
      awaitingStepTransition = false;
    }
  }
  scrollRafId = requestAnimationFrame(tryScroll);
}

function focus(stepId: number, photoId: string) {
  focusedStepId.value = stepId;
  focusedPhotoId.value = photoId;
}

function blur() {
  focusedStepId.value = null;
  focusedPhotoId.value = null;
}

/** Try to move focus to an adjacent step. Returns true if successful. */
function moveToAdjacentStep(direction: "prev" | "next"): boolean {
  const currentStepId = focusedStepId.value;
  if (currentStepId == null) return false;

  const steps = getSteps();
  const orderIdx = steps.findIndex((s) => s.id === currentStepId);
  if (orderIdx < 0) return false;

  const delta = direction === "next" ? 1 : -1;
  for (let i = orderIdx + delta; i >= 0 && i < steps.length; i += delta) {
    const nextStep = steps[i];
    const photos = pagedPhotos(nextStep);
    if (photos.length === 0) continue;

    focusedStepId.value = nextStep.id;
    focusedPhotoId.value =
      direction === "next" ? photos[0] : photos[photos.length - 1];
    awaitingStepTransition = true;
    scrollToStepFn?.(nextStep.id);
    scrollFocusedIntoView();
    return true;
  }

  return false;
}

function move(direction: "prev" | "next") {
  // Block navigation while a cross-step scroll is still settling  -
  // the target step's DOM isn't mounted yet, so advancing would
  // silently skip photos the user can't see.
  if (awaitingStepTransition) return;

  const currentStepId = focusedStepId.value;
  if (currentStepId == null) return;

  const step = getStep(currentStepId);
  if (!step) return;

  const photos = pagedPhotos(step);
  if (photos.length === 0) return;

  const currentIdx = focusedPhotoId.value
    ? photos.indexOf(focusedPhotoId.value)
    : -1;

  if (currentIdx < 0) {
    focusedPhotoId.value =
      direction === "next" ? photos[0] : photos[photos.length - 1];
    return;
  }

  if (direction === "next" && currentIdx === photos.length - 1) {
    moveToAdjacentStep("next");
    return;
  }
  if (direction === "prev" && currentIdx === 0) {
    moveToAdjacentStep("prev");
    return;
  }

  const nextIdx = direction === "next" ? currentIdx + 1 : currentIdx - 1;
  focusedPhotoId.value = photos[nextIdx]!;
  scrollFocusedIntoView();
}

function sendToUnused(): boolean {
  const step =
    focusedStepId.value != null ? getStep(focusedStepId.value) : null;
  const photoId = focusedPhotoId.value;
  if (!step || !photoId) return false;

  const photos = pagedPhotos(step);
  advanceFocus(photos, photos.indexOf(photoId));
  mutateFn?.(step.id, unusedUpdatePayload(step, [...step.unused, photoId]));
  return true;
}

function setAsCover(): boolean {
  const step =
    focusedStepId.value != null ? getStep(focusedStepId.value) : null;
  const photoId = focusedPhotoId.value;
  if (!step || !photoId) return false;

  const photos = pagedPhotos(step);
  advanceFocus(photos, photos.indexOf(photoId));
  mutateFn?.(step.id, coverUpdatePayload(step, photoId));
  return true;
}

const api = {
  focusedStepId: readonly(focusedStepId),
  focusedPhotoId: readonly(focusedPhotoId),
  init,
  dispose,
  focus,
  blur,
  move,
  sendToUnused,
  setAsCover,
};

export function usePhotoFocus() {
  return api;
}
