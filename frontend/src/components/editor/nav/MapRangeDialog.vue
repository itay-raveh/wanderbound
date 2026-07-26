<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import { isoDate, inDateRange, parseLocalDate, SHORT_DATE } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { computed, ref, useId, watch } from "vue";
import { useI18n } from "vue-i18n";
import ChapterStartSelect from "./ChapterStartSelect.vue";

const show = defineModel<boolean>({ required: true });
const props = defineProps<{
  steps: Step[];
  dateRange?: DateRange | null;
}>();
const emit = defineEmits<{
  save: [range: DateRange];
}>();

const { t } = useI18n();
const { countryName, formatDate, formatDateRange } = useUserQuery();
const id = useId();
const startStepId = ref<number | null>(null);
const endStepId = ref<number | null>(null);

const options = computed(() =>
  props.steps.map((step) => ({
    value: step.id,
    label: step.name || step.location.name || String(step.id),
    countryCode: step.location.country_code,
    countryLabel: countryName(step.location.country_code, step.location.detail),
    detail: formatDate(parseLocalDate(step.datetime), SHORT_DATE),
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
  <q-dialog v-model="show" :aria-labelledby="`${id}-title`">
    <q-card class="map-range-dialog">
      <h3
        :id="`${id}-title`"
        class="map-range-title text-weight-semibold text-bright"
      >
        {{ dateRange ? t("nav.editMap") : t("nav.addMap") }}
      </h3>
      <div class="map-range-fields">
        <ChapterStartSelect
          v-model="startStepId"
          :options="options"
          :label="t('nav.startStep')"
        />
        <ChapterStartSelect
          v-model="endStepId"
          :options="endOptions"
          :label="t('nav.endStep')"
        />
      </div>
      <p v-if="selectedRange" class="map-range-summary text-muted">
        <span>{{ selectedRange.label }}</span>
        <span aria-hidden="true">&middot;</span>
        <span>{{ t("nav.stepCount", selectedRange.stepCount) }}</span>
      </p>
      <div class="map-range-actions">
        <q-btn v-close-popup flat no-caps>{{ t("common.cancel") }}</q-btn>
        <q-btn
          class="map-range-save"
          color="primary"
          no-caps
          :disable="!canSave"
          @click="save"
        >
          {{ dateRange ? t("common.save") : t("nav.addMap") }}
        </q-btn>
      </div>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.map-range-dialog {
  width: min(28rem, calc(100vw - 2rem));
  padding: var(--gap-xl);
}

.map-range-title {
  margin: 0 0 var(--gap-lg);
  font-size: var(--type-subtitle);
}

.map-range-fields {
  display: grid;
  gap: var(--gap-md);

  :deep(.chapter-start-select) {
    padding-inline: var(--gap-md);
    border: 1px solid color-mix(in srgb, var(--border-color) 78%, transparent);
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--surface) 76%, transparent);
  }
}

.map-range-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-sm);
  margin: var(--gap-md) var(--gap-xs) 0;
  font-size: var(--type-xs);
}

.map-range-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--gap-sm);
  margin-top: var(--gap-xl);
}
</style>
