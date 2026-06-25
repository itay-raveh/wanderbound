<script lang="ts" setup>
import type { AlbumChapter, StepRead as Step } from "@/client";
import { chapterCanSplit } from "./chapterEditing";
import { useI18n } from "vue-i18n";
import {
  symOutlinedAdd,
  symOutlinedArrowDownward,
  symOutlinedArrowUpward,
  symOutlinedDelete,
} from "@quasar/extras/material-symbols-outlined";
import { computed } from "vue";

const { t } = useI18n();

const props = defineProps<{
  chapters: AlbumChapter[];
  steps: Step[];
  openChapterKey: string | null;
}>();

const emit = defineEmits<{
  selectChapter: [chapterId: string];
  splitChapter: [chapterId: string];
  deleteChapter: [chapterId: string];
  moveChapter: [chapterId: string, direction: -1 | 1];
  adjustBoundary: [
    leftChapterId: string,
    rightChapterId: string,
    firstRightStepId: number,
  ];
}>();

const stepsById = computed(() => new Map(props.steps.map((step) => [step.id, step])));
const splitTargetId = computed(() => {
  const openChapter = props.chapters.find(
    (chapter) => chapter.id === props.openChapterKey,
  );
  if (openChapter && chapterCanSplit(openChapter)) return openChapter.id;
  return props.chapters.find(chapterCanSplit)?.id ?? null;
});

function chapterName(chapter: AlbumChapter, index: number): string {
  return chapter.title || t("chapters.untitled", { number: index + 1 });
}

function stepLabel(stepId: number): string {
  const step = stepsById.value.get(stepId);
  return step?.name || step?.location.name || String(stepId);
}

function boundaryOptions(left: AlbumChapter, right: AlbumChapter) {
  const combined = [...(left.step_ids ?? []), ...(right.step_ids ?? [])];
  return combined.slice(1).map((stepId) => ({
    label: stepLabel(stepId),
    value: stepId,
  }));
}
</script>

<template>
  <section class="chapter-editor" :aria-label="t('chapters.title')">
    <div class="chapter-editor-header">
      <span>{{ t("chapters.title") }}</span>
      <q-btn
        type="button"
        dense
        flat
        round
        class="chapter-action"
        :icon="symOutlinedAdd"
        :aria-label="t('chapters.add')"
        :disable="!splitTargetId"
        @click="splitTargetId && emit('splitChapter', splitTargetId)"
      />
    </div>

    <div class="chapter-outline">
      <template v-for="(chapter, index) in chapters" :key="chapter.id">
        <div
          :class="[
            'chapter-outline-row',
            { active: chapter.id === openChapterKey },
          ]"
        >
          <button
            type="button"
            class="chapter-row-main"
            @click="emit('selectChapter', chapter.id)"
          >
            <span class="chapter-row-title" dir="auto">{{
              chapterName(chapter, index)
            }}</span>
            <span class="chapter-row-count">{{
              t("nav.stepCount", chapter.step_ids?.length ?? 0)
            }}</span>
          </button>

          <div class="chapter-row-actions">
            <q-btn
              type="button"
              dense
              flat
              round
              class="chapter-action"
              :icon="symOutlinedArrowUpward"
              :aria-label="t('chapters.moveUp')"
              :disable="index === 0"
              @click="emit('moveChapter', chapter.id, -1)"
            />
            <q-btn
              type="button"
              dense
              flat
              round
              class="chapter-action"
              :icon="symOutlinedArrowDownward"
              :aria-label="t('chapters.moveDown')"
              :disable="index === chapters.length - 1"
              @click="emit('moveChapter', chapter.id, 1)"
            />
            <q-btn
              type="button"
              dense
              flat
              round
              class="chapter-action"
              :icon="symOutlinedDelete"
              :aria-label="t('chapters.delete')"
              :disable="chapters.length <= 1"
              @click="emit('deleteChapter', chapter.id)"
            />
          </div>
        </div>

        <q-select
          v-if="chapters[index + 1]"
          :model-value="chapters[index + 1].step_ids?.[0]"
          :options="boundaryOptions(chapter, chapters[index + 1])"
          class="chapter-boundary"
          dense
          borderless
          emit-value
          map-options
          options-dense
          :aria-label="t('chapters.boundary')"
          @update:model-value="
            emit('adjustBoundary', chapter.id, chapters[index + 1].id, Number($event))
          "
        />
      </template>
    </div>
  </section>
</template>

<style lang="scss" scoped>
.chapter-editor {
  flex-shrink: 0;
  padding: 0 var(--gap-md-lg) var(--gap-sm);
  border-bottom: 1px solid var(--border-color);
}

.chapter-editor-header {
  display: flex;
  align-items: center;
  min-height: 2.25rem;
  gap: var(--gap-sm);
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;

  > span {
    flex: 1;
  }
}

.chapter-outline {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.chapter-outline-row {
  display: flex;
  align-items: center;
  min-height: 2.25rem;
  border-inline-start: 0.125rem solid transparent;
  border-radius: var(--radius-xs);
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text) 4%, transparent);

  &.active {
    border-inline-start-color: var(--q-primary);
    color: var(--text-bright);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  }
}

.chapter-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: var(--gap-xs);
  border: 0;
  padding: var(--gap-xs) var(--gap-sm);
  color: inherit;
  background: transparent;
  text-align: start;
  cursor: pointer;
}

.chapter-row-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--type-sm);
  font-weight: 650;
}

.chapter-row-count {
  flex-shrink: 0;
  font-size: var(--type-xs);
  color: var(--text-faint);
}

.chapter-row-actions {
  display: flex;
  align-items: center;
  padding-inline-end: var(--gap-xs);
}

.chapter-action {
  color: var(--text-muted);

  &:hover {
    color: var(--text-bright);
  }
}

.chapter-boundary {
  align-self: stretch;
  margin-inline-start: var(--gap-lg);
  margin-block: calc(var(--gap-xs) * -1);
  padding-inline: var(--gap-sm);
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text) 3%, transparent);
  border-radius: var(--radius-xs);
  font-size: var(--type-xs);
}

@media (prefers-reduced-motion: reduce) {
  .chapter-outline-row {
    transition: none;
  }
}
</style>
