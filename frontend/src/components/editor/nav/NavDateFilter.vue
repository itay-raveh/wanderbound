<script lang="ts" setup>
import type { Step } from "@/client";
import { isoDate, inDateRange, datesToRanges, parseLocalDate, toQDate, SHORT_DATE } from "@/utils/date";
import { useDateRangePicker, parseDraftRanges } from "@/composables/useDateRangePicker";
import { useUserQuery } from "@/queries/useUserQuery";
import { useUndoStack } from "@/composables/useUndoStack";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { ref, computed, watch, nextTick } from "vue";
import {
  symOutlinedCalendarMonth,
  symOutlinedKeyboardArrowDown,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const $q = useQuasar();
const undoStack = useUndoStack();
const { formatDateRange } = useUserQuery();

type PopupExpose = { hide: () => void };

const props = defineProps<{
  steps: Step[];
  excludedSteps: number[];
  colors: Record<string, string>;
}>();

const emit = defineEmits<{
  "update:excludedSteps": [ids: number[]];
}>();

const excludedSet = computed(() => new Set(props.excludedSteps));

const dateRangeModel = computed(() => {
  if (!excludedSet.value.size) return null;
  const included = props.steps.filter((s) => !excludedSet.value.has(s.id));
  if (!included.length || included.length === props.steps.length) return null;
  return datesToRanges(included.map((s) => isoDate(s.datetime)))
    .map(([from, to]) => ({ from: toQDate(from), to: toQDate(to) }));
});

const { draft, isOpen, open, close } = useDateRangePicker(() => dateRangeModel.value);

watch(dateRangeModel, (v) => { if (!isOpen.value) draft.value = v ?? null; });

function onPickerClose() {
  const val = close();
  const ranges = parseDraftRanges(val);
  if (!ranges.length) {
    emit("update:excludedSteps", []);
    return;
  }
  const excluded = props.steps
    .filter((s) => !ranges.some((r) => inDateRange(isoDate(s.datetime), r)))
    .map((s) => s.id);
  emit("update:excludedSteps", excluded);
}

const rangeDisplay = computed(() => {
  if (!excludedSet.value.size) return "";
  const included = props.steps.filter((s) => !excludedSet.value.has(s.id));
  if (!included.length || included.length === props.steps.length) return "";
  const dates = included.map((s) => parseLocalDate(s.datetime)).sort((a, b) => a.getTime() - b.getTime());
  return formatDateRange(dates[0]!, dates.at(-1)!, SHORT_DATE);
});

const popupRef = ref<PopupExpose>();

function clearFilter() {
  draft.value = null;
  popupRef.value?.hide();
  void nextTick(() => {
    $q.notify({
      message: t("nav.filterCleared"),
      timeout: 4000,
      actions: [{ label: t("shortcuts.undo"), color: "primary", handler: () => undoStack.undo() }],
    });
  });
}
</script>

<template>
  <button type="button" class="nav-chip" :aria-label="t('nav.dateFilter')" aria-haspopup="dialog" @click.stop>
    <q-icon :name="symOutlinedCalendarMonth" size="var(--type-xs)" />
    <span dir="auto">{{ rangeDisplay || t("album.allDates") }}</span>
    <q-icon :name="symOutlinedKeyboardArrowDown" size="var(--type-xs)" class="chip-chevron" />
    <q-popup-proxy ref="popupRef" transition-show="scale" transition-hide="scale" @before-show="open" @before-hide="onPickerClose">
      <div class="picker-panel">
        <StepDatePicker
          v-model="draft"
          :steps="steps"
          :colors="colors"
          range
          multiple
        />
        <div v-if="excludedSet.size" class="picker-footer">
          <button type="button" class="picker-clear-btn" @click="clearFilter">
            {{ t("nav.clearFilter") }}
          </button>
        </div>
      </div>
    </q-popup-proxy>
  </button>
</template>

<style lang="scss" scoped>
.nav-chip {
  appearance: none;
  background: color-mix(in srgb, var(--text) 8%, transparent);
  border: none;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  flex: 1;
  font: inherit;
  font-size: var(--type-xs);
  color: var(--text);
  cursor: pointer;
  padding: var(--gap-sm) var(--gap-sm-md);
  border-radius: var(--radius-md);
  white-space: nowrap;
  transition: color var(--duration-fast), background var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 18%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.chip-chevron {
  margin-inline-start: auto;
}

.picker-panel {
  display: flex;
  flex-direction: column;
}

.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gap-sm) var(--gap-md);
  border-top: 0.0625rem solid var(--border-color);
  gap: var(--gap-sm);
}

.picker-clear-btn {
  appearance: none;
  background: none;
  border: none;
  font: inherit;
  font-size: var(--type-xs);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--gap-xs) var(--gap-sm);
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast), background var(--duration-fast);
  margin-inline-start: auto;

  &:hover {
    color: var(--danger);
    background: color-mix(in srgb, var(--danger) 10%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--danger) 16%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

@media (pointer: coarse) {
  .nav-chip {
    padding: var(--gap-sm-md) var(--gap-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-chip,
  .picker-clear-btn {
    transition: none;
  }
}
</style>
