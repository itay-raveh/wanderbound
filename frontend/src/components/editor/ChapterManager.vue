<script lang="ts" setup>
import type { AlbumMedia, AlbumMeta, StepRead as Step } from "@/client";
import { useChapterEditor } from "./useChapterEditor";
import {
  symOutlinedAdd,
  symOutlinedCheck,
  symOutlinedDelete,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  album: AlbumMeta;
  steps: Step[];
  media: AlbumMedia[];
}>();

const {
  chapters,
  unassigned,
  coverOptions,
  optionalText,
  addChapter,
  updateChapter,
  deleteChapter,
  rangeDraft,
  stepOptionsFor,
  applyRange,
} = useChapterEditor(props);
</script>

<template>
  <div class="chapter-manager">
    <div class="section-heading row no-wrap items-center">
      <span class="text-muted">{{ t("chapters.title") }}</span>
      <q-btn
        class="add-chapter"
        flat
        dense
        round
        :icon="symOutlinedAdd"
        :disable="!unassigned.length"
        :aria-label="t('chapters.add')"
        @click="addChapter"
      >
        <q-tooltip>{{ t("chapters.add") }}</q-tooltip>
      </q-btn>
    </div>

    <div v-if="unassigned.length" class="unassigned">
      <div class="subheading text-muted">{{ t("chapters.unassigned") }}</div>
      <div class="step-list">
        <span v-for="step in unassigned" :key="step.id" class="step-chip">
          {{ step.name }}
        </span>
      </div>
    </div>

    <q-expansion-item
      v-for="(chapter, index) in chapters"
      :key="chapter.id"
      dense
      class="chapter-item"
      header-class="chapter-header"
      expand-icon-class="text-faint"
      :label="chapter.title || t('chapters.untitled', { number: index + 1 })"
    >
      <div class="chapter-fields">
        <q-input
          :model-value="chapter.title"
          :label="t('chapters.chapterTitle')"
          dense
          borderless
          @update:model-value="
            (value) => updateChapter(index, { title: optionalText(value) })
          "
        />
        <q-input
          :model-value="chapter.subtitle"
          :label="t('chapters.chapterSubtitle')"
          dense
          borderless
          @update:model-value="
            (value) => updateChapter(index, { subtitle: optionalText(value) })
          "
        />
        <q-select
          :model-value="chapter.step_ids"
          :options="stepOptionsFor(chapter)"
          :label="t('chapters.steps')"
          dense
          borderless
          multiple
          emit-value
          map-options
          options-dense
          @update:model-value="
            (value) => updateChapter(index, { step_ids: value })
          "
        />
        <div class="range-helper">
          <q-select
            :model-value="rangeDraft(chapter).from"
            :options="stepOptionsFor(chapter)"
            :label="t('chapters.rangeFrom')"
            dense
            borderless
            emit-value
            map-options
            options-dense
            @update:model-value="(value) => (rangeDraft(chapter).from = value)"
          />
          <q-select
            :model-value="rangeDraft(chapter).to"
            :options="stepOptionsFor(chapter)"
            :label="t('chapters.rangeTo')"
            dense
            borderless
            emit-value
            map-options
            options-dense
            @update:model-value="(value) => (rangeDraft(chapter).to = value)"
          />
          <q-btn
            flat
            dense
            round
            :icon="symOutlinedCheck"
            :aria-label="t('chapters.applyRange')"
            @click="applyRange(index, chapter)"
          >
            <q-tooltip>{{ t("chapters.applyRange") }}</q-tooltip>
          </q-btn>
        </div>
        <q-select
          :model-value="chapter.front_cover_photo"
          :options="coverOptions"
          :label="t('chapters.frontCover')"
          dense
          borderless
          emit-value
          map-options
          options-dense
          @update:model-value="
            (value) => updateChapter(index, { front_cover_photo: value })
          "
        />
        <q-select
          :model-value="chapter.back_cover_photo"
          :options="coverOptions"
          :label="t('chapters.backCover')"
          dense
          borderless
          emit-value
          map-options
          options-dense
          @update:model-value="
            (value) => updateChapter(index, { back_cover_photo: value })
          "
        />
        <q-btn
          flat
          dense
          no-caps
          class="delete-chapter"
          :icon="symOutlinedDelete"
          :label="t('chapters.delete')"
          @click="deleteChapter(index)"
        />
      </div>
    </q-expansion-item>
  </div>
</template>

<style lang="scss" scoped>
.chapter-manager {
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
}

.section-heading {
  justify-content: space-between;
  gap: var(--gap-sm);
  font-size: var(--type-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.unassigned {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.subheading {
  font-size: var(--type-xs);
}

.step-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-xs);
}

.step-chip {
  max-width: 100%;
  padding: var(--gap-xs) var(--gap-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  color: var(--text-muted);
  font-size: var(--type-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chapter-item {
  border-top: 1px solid var(--border-color);
}

.chapter-fields {
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
  padding: 0 var(--gap-sm) var(--gap-md);
}

.range-helper {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: var(--gap-sm);
  align-items: center;
}

.delete-chapter {
  align-self: flex-start;
  color: var(--text-muted);
}
</style>
