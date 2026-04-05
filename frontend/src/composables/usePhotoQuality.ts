import { ref } from "vue";
import type { QualitySummary } from "@/utils/photoQuality";

export const qualitySummary = ref<QualitySummary>({ caution: 0, warning: 0 });

export function setQualitySummary(s: QualitySummary): void {
  const cur = qualitySummary.value;
  if (cur.caution === s.caution && cur.warning === s.warning) return;
  qualitySummary.value = s;
}
