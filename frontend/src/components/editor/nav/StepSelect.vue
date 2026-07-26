<script lang="ts" setup>
import type { StepSelectOption } from "./types";
import { flagUrl } from "@/utils/media";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  options: StepSelectOption[];
  modelValue?: number | null;
  label?: string;
}>();

const selected = computed(
  () =>
    props.options.find((option) => option.value === props.modelValue) ?? null,
);

defineEmits<{
  "update:modelValue": [value: number];
}>();
</script>

<template>
  <q-item class="step-select-item">
    <q-item-section>
      <q-select
        :model-value="modelValue"
        :options="options"
        :label="label ?? t('chapters.startsAt')"
        class="step-select"
        popup-content-class="step-select-popup"
        dense
        borderless
        emit-value
        map-options
        options-dense
        @update:model-value="$emit('update:modelValue', Number($event))"
      >
        <template #selected>
          <div v-if="selected" class="step-select-selected" dir="ltr">
            <img
              :src="flagUrl(selected.countryCode)"
              :alt="selected.countryLabel"
              class="step-select-flag"
            />
            <span class="step-select-label" dir="auto">
              {{ selected.label }}
            </span>
          </div>
        </template>
        <template #option="scope">
          <q-item
            v-bind="scope.itemProps"
            class="step-select-option"
            dir="ltr"
          >
            <q-item-section side class="step-select-option-flag">
              <img
                :src="flagUrl(scope.opt.countryCode)"
                :alt="scope.opt.countryLabel"
                class="step-select-flag"
              />
            </q-item-section>
            <q-item-section class="step-select-option-text">
              <span class="step-select-label" dir="auto">
                {{ scope.opt.label }}
              </span>
              <span v-if="scope.opt.detail" class="step-select-option-detail">
                {{ scope.opt.detail }}
              </span>
            </q-item-section>
          </q-item>
        </template>
      </q-select>
    </q-item-section>
  </q-item>
</template>

<style lang="scss" scoped>
.step-select-item {
  min-height: 3.25rem;
  padding: 0 var(--gap-sm);
  border-radius: var(--radius-sm);
}

.step-select {
  min-width: 0;

  :deep(.q-field__control) {
    min-height: 2.75rem;
    padding-inline: 0;
  }

  :deep(.q-field__label) {
    color: var(--text-muted);
    font-size: var(--type-xs);
    font-weight: 650;
  }

  :deep(.q-field__native) {
    color: var(--text-bright);
    font-size: var(--type-sm);
    font-weight: 600;
  }
}

.step-select-selected,
:global(.step-select-option) {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  min-width: 0;
  text-align: left;
}

.step-select-selected {
  width: 100%;
}

.step-select-flag {
  width: 0.875rem;
  height: 0.625rem;
  flex: 0 0 auto;
  border-radius: var(--radius-xs);
}

.step-select-label {
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.step-select-popup) {
  direction: ltr;
  text-align: left;
}

:global(.step-select-option) {
  min-height: 2.25rem;
  padding-inline: var(--gap-sm);
}

:global(.step-select-option-flag) {
  min-width: unset;
  padding-inline-end: 0;
}

:global(.step-select-option-text) {
  min-width: 0;
}

:global(.step-select-option-detail) {
  color: var(--text-muted);
  font-size: var(--type-xs);
}
</style>
