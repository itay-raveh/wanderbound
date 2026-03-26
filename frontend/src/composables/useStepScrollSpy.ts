import type { Directive } from "vue";
import { readonly, ref } from "vue";

const elements = new Map<number, Element>();
const elementIds = new Map<Element, number>();
const visibleStepId = ref<number | null>(null);
let observer: IntersectionObserver | null = null;
const ratios = new Map<number, number>();

function ensureObserver() {
  if (observer) return;
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const id = elementIds.get(entry.target);
        if (id == null) continue;
        if (entry.isIntersecting) ratios.set(id, entry.intersectionRatio);
        else ratios.delete(id);
      }
      let bestId: number | null = null;
      let bestRatio = 0;
      for (const [id, ratio] of ratios) {
        if (ratio > bestRatio) {
          bestRatio = ratio;
          bestId = id;
        }
      }
      if (bestId == null && ratios.size > 0) {
        bestId = ratios.keys().next().value ?? null;
      }
      if (bestId !== visibleStepId.value) visibleStepId.value = bestId;
    },
    { threshold: [0, 0.25] },
  );

  for (const el of elements.values()) observer.observe(el);
}

function register(id: number, el: Element) {
  elements.set(id, el);
  elementIds.set(el, id);
  observer?.observe(el);
}

function unregister(id: number) {
  const el = elements.get(id);
  if (el) {
    observer?.unobserve(el);
    elements.delete(id);
    elementIds.delete(el);
    ratios.delete(id);
  }
  if (elements.size === 0) {
    observer?.disconnect();
    observer = null;
    visibleStepId.value = null;
  }
}

function scrollTo(id: number) {
  elements.get(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function useStepScrollSpy() {
  ensureObserver();
  return { visibleStepId: readonly(visibleStepId), scrollTo };
}

/**
 * Directive for registering elements with the scroll-spy.
 * Usage: v-spy-step="stepId" (pass undefined to skip registration).
 */
export const vSpyStep: Directive<HTMLElement, number | undefined> = {
  mounted(el, { value }) {
    if (value != null) register(value, el);
  },
  updated(el, { value, oldValue }) {
    if (value === oldValue) return;
    if (oldValue != null) unregister(oldValue);
    if (value != null) register(value, el);
  },
  unmounted(_el, { value }) {
    if (value != null) unregister(value);
  },
};
