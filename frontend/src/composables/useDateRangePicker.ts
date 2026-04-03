import { ref } from "vue";
import { toIso } from "@/utils/date";
import type { DateRange } from "@/client";

type QDateRange = { from: string; to: string };
type DraftValue = (QDateRange | string)[] | QDateRange | string | null;

/** Parse a QDate draft value into sorted ISO DateRange pairs. */
export function parseDraftRanges(val: DraftValue): DateRange[] {
  if (!val) return [];
  const entries = Array.isArray(val) ? val : [val];
  const ranges = entries.map((e): DateRange => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  ranges.sort(([a], [b]) => a.localeCompare(b));
  return ranges;
}

export function useDateRangePicker(toModel: () => DraftValue) {
  const draft = ref<DraftValue>(null);
  const isOpen = ref(false);

  function open() {
    draft.value = toModel();
    isOpen.value = true;
  }

  function close(): DraftValue {
    isOpen.value = false;
    return draft.value;
  }

  return { draft, isOpen, open, close };
}
