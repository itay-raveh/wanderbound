<script lang="ts" setup>
import type { Step } from "@/client";
import { getCountryColor } from "../album/colors";
import { isoDate, qDateNavBounds, toQDate } from "@/utils/date";
import { QDate } from "quasar";
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, useTemplateRef, watchEffect } from "vue";

defineOptions({ inheritAttrs: false });

const props = defineProps<{
  steps: Step[];
  colors: Record<string, string>;
  /** Additional date constraint (merged with the step-dates-only filter). */
  options?: (date: string) => boolean;
}>();

/** Map QDate-format date -> country color hex for steps on that date. */
const dateColorMap = computed(() => {
  const map = new Map<string, string>();
  for (const step of props.steps) {
    const qd = toQDate(isoDate(step.datetime));
    if (!map.has(qd)) {
      map.set(qd, getCountryColor(props.colors, step.location.country_code));
    }
  }
  return map;
});

function hasStep(date: string): boolean {
  return dateColorMap.value.has(date);
}

/** Merged options: must be a step date AND pass the parent's constraint. */
function dateOptions(date: string): boolean {
  return hasStep(date) && (props.options?.(date) ?? true);
}

const nav = computed(() => qDateNavBounds(props.steps));

// --- Dynamic country-colored event dots ---
// QDate's event-color only accepts Quasar palette names, not hex.
// We inject a <style> element with per-color classes (.bg-cc0, .bg-cc1, ...)
// and return those class names from the event-color function.

const uid = getCurrentInstance()!.uid;

const colorClassMap = computed(() => {
  const map = new Map<string, string>();
  let idx = 0;
  for (const hex of new Set(dateColorMap.value.values())) {
    map.set(hex, `cc${uid}-${idx++}`);
  }
  return map;
});

const styleEl = document.createElement("style");
onMounted(() => document.head.appendChild(styleEl));
onBeforeUnmount(() => styleEl.remove());

watchEffect(() => {
  styleEl.textContent = [...colorClassMap.value.entries()]
    .map(([hex, cls]) => `.bg-${cls}{background:${hex}!important}`)
    .join("");
});

function eventColor(date: string): string {
  const hex = dateColorMap.value.get(date);
  if (!hex) return "primary";
  return colorClassMap.value.get(hex) ?? "primary";
}

const dateRef = useTemplateRef<InstanceType<typeof QDate>>("dateRef");
defineExpose({
  setEditingRange: (...args: Parameters<QDate["setEditingRange"]>) => {
    dateRef.value?.setEditingRange(...args);
  },
});
</script>

<template>
  <q-date
    ref="dateRef"
    v-bind="($attrs as any)"
    minimal
    :options="dateOptions"
    :events="hasStep"
    :event-color="eventColor"
    :default-year-month="nav.min"
    :navigation-min-year-month="nav.min"
    :navigation-max-year-month="nav.max"
  />
</template>
