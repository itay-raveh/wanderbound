import type { VirtualItem } from "@tanstack/vue-virtual";
import { ref } from "vue";

/**
 * Pick the virtualizer item whose center is closest to the viewport center.
 * Whichever section dominates the viewport wins - simple and intuitive.
 */
export function pickBestItem<T extends VirtualItem>(
  items: readonly T[],
  scrollY: number,
  scrollMargin: number,
  viewportCenter: number,
): T | null {
  let best: T | null = null;
  let bestDist = Infinity;

  for (const vi of items) {
    const top = vi.start + scrollMargin - scrollY;
    const center = top + vi.size / 2;
    const dist = Math.abs(center - viewportCenter);
    if (dist < bestDist) {
      bestDist = dist;
      best = vi;
    }
  }
  return best;
}

const activeStepId = ref<number | null>(null);
const activeSectionKey = ref<string | null>(null);

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

let scrollOverride: {
  scrollTo: (id: number) => void;
  scrollToSection: (key: string) => boolean;
} | null = null;

function setActive(value: number | string | null) {
  if (value === null) {
    if (activeStepId.value === null && activeSectionKey.value === null) return;
    activeStepId.value = null;
    activeSectionKey.value = null;
  } else if (typeof value === "number") {
    if (activeStepId.value === value && activeSectionKey.value === null) return;
    activeStepId.value = value;
    activeSectionKey.value = null;
  } else {
    if (activeSectionKey.value === value && activeStepId.value === null) return;
    activeStepId.value = null;
    activeSectionKey.value = value;
  }
}

function scrollBehavior(): ScrollBehavior {
  return reducedMotion.matches ? "instant" : "smooth";
}

function scrollTo(id: number) {
  if (scrollOverride) scrollOverride.scrollTo(id);
}

function scrollToSection(key: string): boolean {
  if (scrollOverride) return scrollOverride.scrollToSection(key);
  return false;
}

function setScrollOverride(override: typeof scrollOverride) {
  scrollOverride = override;
}

function resetActiveSection() {
  activeStepId.value = null;
  activeSectionKey.value = null;
  scrollOverride = null;
}

export function useActiveSection() {
  return {
    activeStepId,
    activeSectionKey,
    setActive,
    scrollTo,
    scrollToSection,
    scrollBehavior,
    setScrollOverride,
    resetActiveSection,
  };
}
