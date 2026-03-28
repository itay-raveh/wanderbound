import type { Directive } from "vue";
import { readonly, ref } from "vue";

const elements = new Map<number, Element>();
const elementIds = new Map<Element, number>();
const visibleStepId = ref<number | null>(null);
const visible = new Set<number>();

const sectionEls = new Map<string, Element>();
const sectionIds = new Map<Element, string>();
const visibleSections = new Set<string>();
const visibleSectionKey = ref<string | null>(null);

let observer: IntersectionObserver | null = null;
let rafId = 0;

/** Pick the element whose top edge is closest to the upper quarter of the viewport. */
function pickBest() {
  rafId = 0;
  const target = window.innerHeight * 0.25;
  let bestStepId: number | null = null;
  let bestSectionKey: string | null = null;
  let bestDist = Infinity;

  function consider(el: Element, stepId: number | null, secKey: string | null) {
    const dist = Math.abs(el.getBoundingClientRect().top - target);
    if (dist < bestDist) { bestDist = dist; bestStepId = stepId; bestSectionKey = secKey; }
  }

  for (const id of visible) { const el = elements.get(id); if (el) consider(el, id, null); }
  for (const key of visibleSections) { const el = sectionEls.get(key); if (el) consider(el, null, key); }

  visibleStepId.value = bestStepId;
  visibleSectionKey.value = bestSectionKey;
}

function createObserver() {
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const stepId = elementIds.get(entry.target);
        if (stepId != null) {
          if (entry.isIntersecting) visible.add(stepId);
          else visible.delete(stepId);
          continue;
        }
        const secKey = sectionIds.get(entry.target);
        if (secKey != null) {
          if (entry.isIntersecting) visibleSections.add(secKey);
          else visibleSections.delete(secKey);
        }
      }
      if (!rafId) rafId = requestAnimationFrame(pickBest);
    },
    { threshold: 0 },
  );
  for (const el of elements.values()) observer.observe(el);
  for (const el of sectionEls.values()) observer.observe(el);
}

function register(id: number, el: Element) {
  elements.set(id, el);
  elementIds.set(el, id);
  if (!observer) createObserver();
  observer!.observe(el);
}

function maybeDisconnect() {
  if (elements.size === 0 && sectionEls.size === 0) {
    observer?.disconnect();
    observer = null;
    visibleStepId.value = null;
    visibleSectionKey.value = null;
  }
}

function unregister(id: number) {
  const el = elements.get(id);
  if (el) {
    observer?.unobserve(el);
    elements.delete(id);
    elementIds.delete(el);
    visible.delete(id);
  }
  maybeDisconnect();
}

function registerSection(key: string, el: Element) {
  sectionEls.set(key, el);
  sectionIds.set(el, key);
  if (!observer) createObserver();
  observer!.observe(el);
}

function unregisterSection(key: string) {
  const el = sectionEls.get(key);
  if (el) {
    observer?.unobserve(el);
    sectionEls.delete(key);
    sectionIds.delete(el);
    visibleSections.delete(key);
  }
  maybeDisconnect();
}

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

let scrollOverride: {
  scrollTo: (id: number) => void;
  scrollToSection: (key: string) => boolean;
} | null = null;

function scrollBehavior(): ScrollBehavior {
  return reducedMotion.matches ? "instant" : "smooth";
}

function scrollTo(id: number) {
  if (scrollOverride) { scrollOverride.scrollTo(id); return; }
  elements.get(id)?.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
}

function scrollToSection(key: string): boolean {
  if (scrollOverride) return scrollOverride.scrollToSection(key);
  const el = sectionEls.get(key);
  if (!el) return false;
  el.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  return true;
}

function setScrollOverride(override: typeof scrollOverride) {
  scrollOverride = override;
}

function resetScrollSpy() {
  cancelAnimationFrame(rafId);
  rafId = 0;
  observer?.disconnect();
  observer = null;
  elements.clear();
  elementIds.clear();
  visible.clear();
  sectionEls.clear();
  sectionIds.clear();
  visibleSections.clear();
  visibleStepId.value = null;
  visibleSectionKey.value = null;
  scrollOverride = null;
}

export function useStepScrollSpy() {
  if (!observer && (elements.size > 0 || sectionEls.size > 0)) createObserver();
  return { visibleStepId: readonly(visibleStepId), visibleSectionKey: readonly(visibleSectionKey), scrollTo, scrollToSection, scrollBehavior, setScrollOverride, resetScrollSpy };
}

type SpyValue = number | string | undefined;

function spyMount(el: HTMLElement, value: SpyValue) {
  if (typeof value === "number") register(value, el);
  else if (typeof value === "string") registerSection(value, el);
}

function spyUnmount(value: SpyValue | null) {
  if (typeof value === "number") unregister(value);
  else if (typeof value === "string") unregisterSection(value);
}

/**
 * Directive for registering elements with the scroll-spy.
 * Pass a step ID (number) to track as a step, a section key (string) to track
 * as a section (map/hike), or undefined to skip registration.
 */
export const vSpyStep: Directive<HTMLElement, SpyValue> = {
  mounted(el, { value }) {
    spyMount(el, value);
  },
  updated(el, { value, oldValue }) {
    if (value === oldValue) return;
    spyUnmount(oldValue);
    spyMount(el, value);
  },
  unmounted(_el, { value }) {
    spyUnmount(value);
  },
};
