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

const includedSteps = computed(() => {
  if (!excludedSet.value.size) return null;
  const filtered = props.steps.filter((s) => !excludedSet.value.has(s.id));
  return filtered.length && filtered.length < props.steps.length ? filtered : null;
});

const dateRangeModel = computed(() => {
  const steps = includedSteps.value;
  if (!steps) return null;
  return datesToRanges(steps.map((s) => isoDate(s.datetime)))
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
  const steps = includedSteps.value;
  if (!steps) return "";
  const dates = steps.map((s) => parseLocalDate(s.datetime)).sort((a, b) => a.getTime() - b.getTime());
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
@use "picker";
</style>
