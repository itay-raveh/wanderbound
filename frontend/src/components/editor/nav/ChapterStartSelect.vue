<script lang="ts" setup>
import type { ChapterStartOption } from "./types";
import { flagUrl } from "@/utils/media";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  options: ChapterStartOption[];
  modelValue?: number | null;
}>();

const selected = computed(
  () => props.options.find((option) => option.value === props.modelValue) ?? null,
);

defineEmits<{
  "update:modelValue": [value: number];
}>();
</script>

<template>
  <q-select
    :model-value="modelValue"
    :options="options"
    :label="t('chapters.startsAt')"
    class="chapter-start-select"
    popup-content-class="chapter-start-popup"
    dense
    borderless
    emit-value
    map-options
    options-dense
    @update:model-value="$emit('update:modelValue', Number($event))"
  >
    <template #selected>
      <div v-if="selected" class="chapter-start-selected" dir="ltr">
        <img
          :src="flagUrl(selected.countryCode)"
          :alt="selected.countryLabel"
          class="chapter-start-flag"
        />
        <span class="chapter-start-label" dir="auto">
          {{ selected.label }}
        </span>
      </div>
    </template>
    <template #option="scope">
      <q-item v-bind="scope.itemProps" class="chapter-start-option" dir="ltr">
        <q-item-section side class="chapter-start-option-flag">
          <img
            :src="flagUrl(scope.opt.countryCode)"
            :alt="scope.opt.countryLabel"
            class="chapter-start-flag"
          />
        </q-item-section>
        <q-item-section class="chapter-start-option-text">
          <span class="chapter-start-label" dir="auto">
            {{ scope.opt.label }}
          </span>
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<style lang="scss" scoped>
.chapter-start-select {
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

.chapter-start-selected,
:global(.chapter-start-option) {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  min-width: 0;
  text-align: left;
}

.chapter-start-selected {
  width: 100%;
}

.chapter-start-flag {
  width: 0.875rem;
  height: 0.625rem;
  flex: 0 0 auto;
  border-radius: var(--radius-xs);
}

.chapter-start-label {
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.chapter-start-popup) {
  direction: ltr;
  text-align: left;
}

:global(.chapter-start-option) {
  min-height: 2.25rem;
  padding-inline: var(--gap-sm);
}

:global(.chapter-start-option-flag) {
  min-width: unset;
  padding-inline-end: 0;
}

:global(.chapter-start-option-text) {
  min-width: 0;
}
</style>
