import { ref, shallowRef, triggerRef } from "vue";
import type { QualitySummary } from "@/utils/photoQuality";

export const qualitySummary = ref<QualitySummary>({ caution: 0, warning: 0 });

export function setQualitySummary(s: QualitySummary): void {
  const cur = qualitySummary.value;
  if (cur.caution === s.caution && cur.warning === s.warning) return;
  qualitySummary.value = s;
}

const badges = shallowRef(new Set<HTMLElement>());
let cursor = 0;

export function registerQualityBadge(el: HTMLElement): () => void {
  badges.value.add(el);
  triggerRef(badges);
  return () => {
    badges.value.delete(el);
    triggerRef(badges);
  };
}

export function jumpToNextQualityBadge(): {
  index: number;
  total: number;
} | null {
  const live = Array.from(badges.value).filter((el) => el.isConnected);
  if (live.length === 0) return null;
  const index = cursor % live.length;
  cursor = (index + 1) % live.length;
  const target = live[index];
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.focus({ preventScroll: true });
  return { index, total: live.length };
}
