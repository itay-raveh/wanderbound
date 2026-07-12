<script lang="ts" setup>
import { flagUrl } from "@/utils/media";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import {
  symOutlinedCallMerge,
  symOutlinedCallSplit,
} from "@quasar/extras/material-symbols-outlined";

type StartOption = {
  label: string;
  value: number;
  countryCode: string;
  countryLabel: string;
};

const { t } = useI18n();

const props = defineProps<{
  canDelete?: boolean;
  canSplit?: boolean;
  mergeTarget?: "previous" | "next";
  startOptions?: StartOption[];
  startStepId?: number | null;
}>();

const selectedStartOption = computed(
  () =>
    props.startOptions?.find((option) => option.value === props.startStepId) ??
    null,
);

defineEmits<{
  splitChapter: [];
  deleteChapter: [];
  adjustBoundary: [firstStepId: number];
}>();
</script>

<template>
  <q-list dense class="chapter-action-menu">
    <q-item v-if="startOptions?.length" class="chapter-start-item">
      <q-item-section>
        <q-select
          :model-value="startStepId"
          :options="startOptions"
          :label="t('chapters.startsAt')"
          class="chapter-start-select"
          popup-content-class="chapter-start-popup"
          dense
          borderless
          emit-value
          map-options
          options-dense
          @update:model-value="$emit('adjustBoundary', Number($event))"
        >
          <template #selected>
            <div
              v-if="selectedStartOption"
              class="chapter-start-selected"
              dir="ltr"
            >
              <img
                :src="flagUrl(selectedStartOption.countryCode)"
                :alt="selectedStartOption.countryLabel"
                class="chapter-start-flag"
              />
              <span class="chapter-start-label" dir="auto">
                {{ selectedStartOption.label }}
              </span>
            </div>
          </template>
          <template #option="scope">
            <q-item
              v-bind="scope.itemProps"
              class="chapter-start-option"
              dir="ltr"
            >
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
      </q-item-section>
    </q-item>
    <q-separator v-if="startOptions?.length" class="chapter-menu-separator" />
    <q-item
      clickable
      :disable="!canSplit"
      v-close-popup
      class="chapter-menu-action"
      @click="$emit('splitChapter')"
    >
      <q-item-section side class="chapter-menu-icon">
        <q-icon :name="symOutlinedCallSplit" />
      </q-item-section>
      <q-item-section>{{ t("chapters.split") }}</q-item-section>
    </q-item>
    <q-separator class="chapter-menu-separator" />
    <q-item
      clickable
      :disable="!canDelete"
      v-close-popup
      class="chapter-menu-action"
      @click="$emit('deleteChapter')"
    >
      <q-item-section side class="chapter-menu-icon">
        <q-icon :name="symOutlinedCallMerge" />
      </q-item-section>
      <q-item-section>
        {{
          t(
            mergeTarget === "next"
              ? "chapters.mergeNext"
              : "chapters.mergePrevious",
          )
        }}
      </q-item-section>
    </q-item>
  </q-list>
</template>

<style lang="scss" scoped>
.chapter-action-menu {
  min-width: 13.5rem;
  padding: var(--gap-xs);
  color: var(--text-bright);
}

.chapter-start-item {
  min-height: 3.25rem;
  padding: 0 var(--gap-sm);
  border-radius: var(--radius-sm);

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

.chapter-start-select {
  min-width: 0;
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

.chapter-menu-separator {
  margin: var(--gap-xs) 0;
  background: var(--border-color);
}

.chapter-menu-action {
  min-height: 2.5rem;
  padding-inline: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 600;

  &:hover {
    background: color-mix(in srgb, var(--q-primary) 14%, transparent);
  }
}

.chapter-menu-icon {
  min-width: 2rem;
  padding-inline-end: var(--gap-sm);
  color: var(--text-muted);
}
</style>
