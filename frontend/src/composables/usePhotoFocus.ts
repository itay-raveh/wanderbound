import type { Step } from "@/client";
import { ref, type InjectionKey, type Ref, readonly } from "vue";

export const STEP_ID_KEY: InjectionKey<number> = Symbol("step-id");

export interface StepFocusContext {
  step: Ref<Step>;
  onCoverUpdate: (cover: string) => void;
  onUnusedUpdate: (unused: string[]) => void;
}

const focusedStepId = ref<number | null>(null);
const focusedPhotoId = ref<string | null>(null);
const registry = new Map<number, StepFocusContext>();
let getStepOrder: () => number[] = () => [];

function pagedPhotos(step: Step): string[] {
  return step.pages.flat();
}

function getContext() {
  if (focusedStepId.value == null) return null;
  return registry.get(focusedStepId.value) ?? null;
}

function advanceFocus(photos: string[], removedIdx: number) {
  if (removedIdx < 0 || photos.length <= 1) {
    focusedStepId.value = null;
    focusedPhotoId.value = null;
    return;
  }
  const focusIdx = removedIdx < photos.length - 1 ? removedIdx + 1 : removedIdx - 1;
  focusedPhotoId.value = photos[focusIdx]!;
}

function register(stepId: number, context: StepFocusContext) {
  registry.set(stepId, context);
}

function unregister(stepId: number) {
  registry.delete(stepId);
  if (focusedStepId.value === stepId) {
    focusedStepId.value = null;
    focusedPhotoId.value = null;
  }
}

function setStepOrder(getter: () => number[]) {
  getStepOrder = getter;
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

  const order = getStepOrder();
  const orderIdx = order.indexOf(currentStepId);
  if (orderIdx < 0) return false;

  const delta = direction === "next" ? 1 : -1;
  for (let i = orderIdx + delta; i >= 0 && i < order.length; i += delta) {
    const nextStepId = order[i]!;
    const nextCtx = registry.get(nextStepId);
    if (!nextCtx) continue;

    const photos = pagedPhotos(nextCtx.step.value);
    if (photos.length === 0) continue;

    focusedStepId.value = nextStepId;
    focusedPhotoId.value = direction === "next" ? photos[0]! : photos[photos.length - 1]!;
    return true;
  }

  return false;
}

function move(direction: "prev" | "next") {
  const ctx = getContext();
  if (!ctx) return;

  const photos = pagedPhotos(ctx.step.value);
  if (photos.length === 0) return;

  const currentIdx = focusedPhotoId.value
    ? photos.indexOf(focusedPhotoId.value)
    : -1;

  if (currentIdx < 0) {
    focusedPhotoId.value = direction === "next" ? photos[0]! : photos[photos.length - 1]!;
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
}

function sendToUnused(): boolean {
  const ctx = getContext();
  const photoId = focusedPhotoId.value;
  if (!ctx || !photoId) return false;

  const s = ctx.step.value;
  const photos = pagedPhotos(s);
  advanceFocus(photos, photos.indexOf(photoId));
  ctx.onUnusedUpdate([...s.unused, photoId]);
  return true;
}

function setAsCover(): boolean {
  const ctx = getContext();
  const photoId = focusedPhotoId.value;
  if (!ctx || !photoId) return false;

  const photos = pagedPhotos(ctx.step.value);
  advanceFocus(photos, photos.indexOf(photoId));
  ctx.onCoverUpdate(photoId);
  return true;
}

const api = {
  focusedStepId: readonly(focusedStepId),
  focusedPhotoId: readonly(focusedPhotoId),
  register,
  unregister,
  setStepOrder,
  focus,
  blur,
  move,
  sendToUnused,
  setAsCover,
};

export function usePhotoFocus() {
  return api;
}
