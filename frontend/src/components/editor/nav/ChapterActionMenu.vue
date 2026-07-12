<script lang="ts" setup>
import type { ChapterStartOption } from "./types";
import { useI18n } from "vue-i18n";
import ChapterStartSelect from "./ChapterStartSelect.vue";
import {
  symOutlinedCallMerge,
  symOutlinedCallSplit,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

const props = defineProps<{
  canDelete?: boolean;
  canSplit?: boolean;
  mergeTarget?: "previous" | "next";
  startOptions?: ChapterStartOption[];
  startStepId?: number | null;
}>();

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
        <ChapterStartSelect
          :model-value="props.startStepId"
          :options="startOptions"
          @update:model-value="$emit('adjustBoundary', $event)"
        />
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
