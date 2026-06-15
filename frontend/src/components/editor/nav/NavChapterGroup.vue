<script lang="ts" setup>
import type {
  AlbumChapter,
  DateRange,
  StepRead as Step,
} from "@/client";
import type { ChapterVisit } from "./types";
import NavMapItem from "./NavMapItem.vue";
import NavStepItem from "./NavStepItem.vue";
import { entryKey } from "./useAlbumNavGroups";
import {
  symOutlinedAdd,
  symOutlinedCheck,
  symOutlinedDelete,
  symOutlinedEdit,
} from "@quasar/extras/material-symbols-outlined";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

type Option<T> = {
  label: string;
  value: T;
  disable?: boolean;
};

type RangeDraft = {
  from: number | null;
  to: number | null;
};

const props = defineProps<{
  group: ChapterVisit;
  open: boolean;
  activeStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
  formatStepDate: (date: Date) => string;
  sectionKeyMatchesRange: (key: string | null, range: DateRange) => boolean;
  lazyRoot?: HTMLElement | null;
  coverOptions: Option<string>[];
  stepOptionsFor: (chapter: AlbumChapter) => Option<number>[];
  rangeDraft: (chapter: AlbumChapter) => RangeDraft;
  optionalText: (value: string | number | null) => string | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [range: DateRange];
  toggleStep: [id: number];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
  addChapter: [];
  updateChapter: [index: number, patch: Partial<AlbumChapter>];
  deleteChapter: [index: number];
  applyRange: [index: number, chapter: AlbumChapter];
}>();

const editing = ref(false);

const chapter = computed(() => props.group.chapter);
const chapterIndex = computed(() => props.group.chapterIndex);
const activeStepOptions = computed(() =>
  chapter.value ? props.stepOptionsFor(chapter.value) : [],
);
const activeRangeDraft = computed(() =>
  chapter.value ? props.rangeDraft(chapter.value) : { from: null, to: null },
);

function updateChapter(patch: Partial<AlbumChapter>) {
  if (chapterIndex.value == null) return;
  emit("updateChapter", chapterIndex.value, patch);
}

function deleteChapter() {
  if (chapterIndex.value == null) return;
  emit("deleteChapter", chapterIndex.value);
}

function applyRange() {
  if (!chapter.value || chapterIndex.value == null) return;
  emit("applyRange", chapterIndex.value, chapter.value);
}

function updateRangeDraft(field: keyof RangeDraft, value: number | null) {
  activeRangeDraft.value[field] = value;
}

function stepCountLabel(chapter: AlbumChapter): string {
  return t("chapters.stepCount", { count: chapter.step_ids?.length ?? 0 });
}

function coverDisplay(name: string | null): string {
  if (!name) return "";
  if (name.length <= 28) return name;
  return `${name.slice(0, 12)}...${name.slice(-12)}`;
}
</script>

<template>
  <q-expansion-item
    dense
    :data-chapter-group="group.key"
    :model-value="open"
    header-class="chapter-group-header"
    expand-icon-class="text-faint"
    @update:model-value="$emit('toggleOpen')"
  >
    <template #header>
      <q-item-section class="chapter-group-name" dir="auto">
        {{ group.name }}
      </q-item-section>
      <q-item-section side class="chapter-count text-muted">
        {{ group.stepIds.length }}
      </q-item-section>
      <q-item-section side class="chapter-actions">
        <q-btn
          v-if="group.isUnassigned"
          class="chapter-action"
          flat
          dense
          round
          :icon="symOutlinedAdd"
          :aria-label="t('chapters.add')"
          @click.stop="$emit('addChapter')"
        >
          <q-tooltip>{{ t("chapters.add") }}</q-tooltip>
        </q-btn>
        <q-btn
          v-else
          class="chapter-action"
          flat
          dense
          round
          :icon="symOutlinedEdit"
          :aria-label="t('chapters.edit')"
          @click.stop="editing = !editing"
        >
          <q-tooltip>{{ t("chapters.edit") }}</q-tooltip>
        </q-btn>
      </q-item-section>
    </template>

    <div v-if="chapter && editing" class="chapter-editor">
      <q-input
        :model-value="chapter.title"
        :label="t('chapters.chapterTitle')"
        dense
        borderless
        @update:model-value="
          (value) => updateChapter({ title: optionalText(value) })
        "
      />
      <q-input
        :model-value="chapter.subtitle"
        :label="t('chapters.chapterSubtitle')"
        dense
        borderless
        @update:model-value="
          (value) => updateChapter({ subtitle: optionalText(value) })
        "
      />
      <q-select
        :model-value="chapter.step_ids"
        :options="activeStepOptions"
        :display-value="stepCountLabel(chapter)"
        :label="t('chapters.steps')"
        dense
        borderless
        multiple
        emit-value
        map-options
        options-dense
        @update:model-value="(value) => updateChapter({ step_ids: value })"
      />
      <div class="range-helper">
        <q-select
          :model-value="activeRangeDraft.from"
          :options="activeStepOptions"
          :label="t('chapters.rangeFrom')"
          dense
          borderless
          emit-value
          map-options
          options-dense
          @update:model-value="(value) => updateRangeDraft('from', value)"
        />
        <q-select
          :model-value="activeRangeDraft.to"
          :options="activeStepOptions"
          :label="t('chapters.rangeTo')"
          dense
          borderless
          emit-value
          map-options
          options-dense
          @update:model-value="(value) => updateRangeDraft('to', value)"
        />
        <q-btn
          flat
          dense
          round
          :icon="symOutlinedCheck"
          :aria-label="t('chapters.applyRange')"
          @click="applyRange"
        >
          <q-tooltip>{{ t("chapters.applyRange") }}</q-tooltip>
        </q-btn>
      </div>
      <q-select
        :model-value="chapter.front_cover_photo"
        :options="coverOptions"
        :display-value="coverDisplay(chapter.front_cover_photo)"
        :label="t('chapters.frontCover')"
        dense
        borderless
        emit-value
        map-options
        options-dense
        @update:model-value="
          (value) => updateChapter({ front_cover_photo: value })
        "
      />
      <q-select
        :model-value="chapter.back_cover_photo"
        :options="coverOptions"
        :display-value="coverDisplay(chapter.back_cover_photo)"
        :label="t('chapters.backCover')"
        dense
        borderless
        emit-value
        map-options
        options-dense
        @update:model-value="
          (value) => updateChapter({ back_cover_photo: value })
        "
      />
      <q-btn
        flat
        dense
        no-caps
        class="delete-chapter"
        :icon="symOutlinedDelete"
        :label="t('chapters.delete')"
        @click="deleteChapter"
      />
    </div>

    <template v-for="entry in group.entries" :key="entryKey(entry)">
      <NavMapItem
        v-if="entry.type === 'map'"
        :data-nav-section="entry.key"
        :date-range="entry.dateRange"
        :range-idx="entry.rangeIdx"
        :active="sectionKeyMatchesRange(activeSectionKey, entry.dateRange)"
        :steps="steps"
        :colors="colors"
        :format-map-range="formatMapRange"
        @click="$emit('scrollToMap', entry.dateRange)"
        @delete="$emit('deleteMap', entry.rangeIdx)"
        @date-change="
          (idx: number, range: DateRange) => $emit('mapDateChange', idx, range)
        "
      />
      <NavStepItem
        v-else
        :data-nav-step="entry.item.id"
        :name="entry.item.name"
        :date="formatStepDate(entry.item.date)"
        :thumb="entry.item.thumb"
        :color="entry.item.color"
        :active="activeStepId === entry.item.id"
        :hidden="hiddenSet.has(entry.item.id)"
        :lazy-root="lazyRoot ?? null"
        @click="$emit('scrollToStep', entry.item.id)"
        @toggle="$emit('toggleStep', entry.item.id)"
      />
    </template>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
:deep(.chapter-group-header) {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
}

.chapter-group-name {
  min-width: 0;
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.chapter-count {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

.chapter-actions {
  padding-inline-start: var(--gap-xs);
}

.chapter-action {
  color: var(--text-muted);
}

.chapter-editor {
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg) var(--gap-md);
  border-top: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  background: color-mix(in srgb, var(--text) 4%, transparent);
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
