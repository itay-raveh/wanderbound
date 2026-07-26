<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import PromptDialog from "@/components/ui/PromptDialog.vue";
import { isoDate, inDateRange, parseLocalDate, SHORT_DATE } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { symOutlinedMap } from "@quasar/extras/material-symbols-outlined";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import StepSelect from "./StepSelect.vue";

const show = defineModel<boolean>({ required: true });
const props = defineProps<{
  steps: Step[];
  dateRange?: DateRange | null;
}>();
const emit = defineEmits<{
  save: [range: DateRange];
}>();

const { t } = useI18n();
const { countryName, formatDateRange } = useUserQuery();
const startStepId = ref<number | null>(null);
const endStepId = ref<number | null>(null);

const options = computed(() =>
  props.steps.map((step) => ({
    value: step.id,
    label: step.name || step.location.name || String(step.id),
    countryCode: step.location.country_code,
    countryLabel: countryName(step.location.country_code, step.location.detail),
  })),
);

const endOptions = computed(() => {
  const startIndex = props.steps.findIndex(
    (step) => step.id === startStepId.value,
  );
  return startIndex < 0 ? options.value : options.value.slice(startIndex);
});

watch(show, (isOpen) => {
  if (!isOpen) return;
  const rangeSteps = props.dateRange
    ? props.steps.filter((step) =>
        inDateRange(isoDate(step.datetime), props.dateRange!),
      )
    : props.steps;
  startStepId.value = rangeSteps[0]?.id ?? null;
  endStepId.value = rangeSteps.at(-1)?.id ?? null;
});

watch(startStepId, (startId) => {
  const startIndex = props.steps.findIndex((step) => step.id === startId);
  const endIndex = props.steps.findIndex((step) => step.id === endStepId.value);
  if (startIndex >= 0 && endIndex < startIndex) endStepId.value = startId;
});

const canSave = computed(
  () => startStepId.value != null && endStepId.value != null,
);

const selectedRange = computed(() => {
  const startIndex = props.steps.findIndex(
    (step) => step.id === startStepId.value,
  );
  const endIndex = props.steps.findIndex((step) => step.id === endStepId.value);
  if (startIndex < 0 || endIndex < startIndex) return null;
  return {
    label: formatDateRange(
      parseLocalDate(props.steps[startIndex].datetime),
      parseLocalDate(props.steps[endIndex].datetime),
      SHORT_DATE,
    ),
    stepCount: endIndex - startIndex + 1,
  };
});

function save() {
  const start = props.steps.find((step) => step.id === startStepId.value);
  const end = props.steps.find((step) => step.id === endStepId.value);
  if (!start || !end) return;
  emit("save", [isoDate(start.datetime), isoDate(end.datetime)]);
  show.value = false;
}
</script>

<template>
  <PromptDialog
    v-model="show"
    :icon="symOutlinedMap"
    variant="primary"
    :title="dateRange ? t('nav.editMap') : t('nav.addMap')"
    body=""
    :confirm-label="dateRange ? t('common.save') : t('nav.addMap')"
    :cancel-label="t('common.cancel')"
    :confirm-disabled="!canSave"
    @confirm="save"
  >
    <div class="map-range-content">
      <q-list dense class="map-range-fields">
        <StepSelect
          v-model="startStepId"
          :options="options"
          :label="t('nav.startStep')"
        />
        <q-separator class="map-range-field-separator" />
        <StepSelect
          v-model="endStepId"
          :options="endOptions"
          :label="t('nav.endStep')"
        />
      </q-list>
      <p v-if="selectedRange" class="map-range-summary text-muted">
        <span>{{ selectedRange.label }}</span>
        <span aria-hidden="true">&middot;</span>
        <span>{{ t("nav.stepCount", selectedRange.stepCount) }}</span>
      </p>
    </div>
  </PromptDialog>
</template>

<style lang="scss" scoped>
.map-range-content {
  width: min(24rem, calc(100vw - 5.5rem));
  margin-bottom: var(--gap-lg);
  text-align: start;
}

.map-range-fields {
  color: var(--text-bright);
}

.map-range-field-separator {
  margin: var(--gap-xs) 0;
  background: var(--border-color);
}

.map-range-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-sm);
  margin: var(--gap-md) var(--gap-xs) 0;
  font-size: var(--type-xs);
}
</style>
