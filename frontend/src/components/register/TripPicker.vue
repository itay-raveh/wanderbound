<script lang="ts" setup>
import type { TripChoice } from "@/client";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  choices: TripChoice[];
  modelValue: string[];
  submitting: boolean;
  error: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: string[]];
  submit: [];
}>();
const { t } = useI18n();
const options = computed(() =>
  props.choices.map(({ id, label }) => ({ value: id, label })),
);
</script>

<template>
  <section class="trip-picker" aria-labelledby="trip-picker-title">
    <h2 id="trip-picker-title" class="text-h6 text-weight-bold">
      {{ t("register.tripPicker.title") }}
    </h2>
    <p class="text-body2 text-muted">
      {{ t("register.tripPicker.body") }}
    </p>
    <q-select
      :model-value="modelValue"
      :options="options"
      multiple
      emit-value
      map-options
      use-chips
      outlined
      :label="t('register.tripPicker.label')"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <p v-if="error" class="text-negative text-caption" role="alert">
      {{ t("register.tripPicker.error") }}
    </p>
    <div class="picker-actions row items-center justify-between">
      <span class="text-caption text-muted" aria-live="polite">
        {{ t("register.tripPicker.selected", modelValue.length) }}
      </span>
      <q-btn
        color="primary"
        :label="t('register.tripPicker.continue')"
        :loading="submitting"
        :disable="modelValue.length === 0 || submitting"
        @click="emit('submit')"
      />
    </div>
  </section>
</template>

<style scoped>
.trip-picker {
  display: grid;
  gap: var(--gap-lg);
}

.trip-picker > * {
  margin: 0;
}

.picker-actions {
  gap: var(--gap-md-lg);
}
</style>
