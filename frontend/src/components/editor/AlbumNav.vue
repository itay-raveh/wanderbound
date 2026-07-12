<script lang="ts" setup>
import type { AlbumNavProps } from "./nav/types";
import { useAlbumNavScrollSync } from "./nav/useAlbumNavScrollSync";
import { useAlbumNavModel } from "./nav/useAlbumNavModel";
import { ref } from "vue";
import NavMapRanges from "./nav/NavMapRanges.vue";
import NavChapterGroup from "./nav/NavChapterGroup.vue";
import { symOutlinedFlightTakeoff } from "@quasar/extras/material-symbols-outlined";

const props = withDefaults(
  defineProps<AlbumNavProps>(),
  {
    albumIds: () => [],
    hiddenSteps: () => [],
    hiddenHeaders: () => [],
    colors: () => ({}),
    mapsRanges: () => [],
  },
);

const selectedAlbumId = defineModel<string | null>("albumId");

const listRef = ref<HTMLElement>();
const {
  t,
  albumOptions,
  hiddenSet,
  hiddenHeaderSet,
  albumColors,
  chapterGroups,
  chapterRows,
  openChapterKey,
  formatMapRange,
  onMapsRangesChange,
  toggleStep,
  toggleHeader,
  toggleChapter,
  onSplitChapter,
  onDeleteChapter,
  onAdjustChapterBoundaryFromRow,
  deleteMap,
  mapDateChange,
} = useAlbumNavModel(props, selectedAlbumId);
const {
  activeStepId,
  activeSectionKey,
  scrollToStep,
  scrollToMap,
  scrollToHeader,
} = useAlbumNavScrollSync({
  chapterGroups,
  openChapterKey,
  listRef,
});
</script>

<template>
  <nav class="album-nav" :aria-label="t('nav.steps')">
    <q-select
      v-if="albumIds.length"
      v-model="selectedAlbumId"
      :options="albumOptions"
      :aria-label="t('nav.selectAlbum')"
      class="nav-album-select"
      dense
      outlined
      options-dense
      emit-value
      map-options
    >
      <template #prepend>
        <q-icon
          :name="symOutlinedFlightTakeoff"
          size="var(--type-md)"
          class="rtl-flip"
        />
      </template>
      <template #selected-item="{ opt }">
        <span dir="ltr" class="album-select-label">{{ opt.label }}</span>
      </template>
    </q-select>

    <div v-if="steps.length" class="nav-controls">
      <NavMapRanges
        :steps="steps"
        :maps-ranges="mapsRanges"
        :colors="albumColors"
        @update:maps-ranges="onMapsRangesChange"
      />
    </div>

    <div ref="listRef" class="nav-list">
      <template v-for="(row, index) in chapterRows" :key="row.group.key">
        <NavChapterGroup
          :group="row.group"
          :open="openChapterKey === row.group.key"
          :active-step-id="activeStepId"
          :active-section-key="activeSectionKey"
          :hidden-set="hiddenSet"
          :hidden-header-set="hiddenHeaderSet"
          :steps="steps"
          :colors="albumColors"
          :format-map-range="formatMapRange"
          :lazy-root="listRef ?? null"
          :can-delete="row.canDelete"
          :can-split="row.canSplit"
          :merge-target="row.mergeTarget"
          :start-step-id="row.startStepId"
          :start-options="row.startOptions"
          @toggle-open="toggleChapter(row.group)"
          @split-chapter="onSplitChapter(row.group.chapter.id)"
          @delete-chapter="onDeleteChapter(row.group.chapter.id)"
          @adjust-boundary="onAdjustChapterBoundaryFromRow(index, $event)"
          @scroll-to-step="scrollToStep"
          @scroll-to-map="scrollToMap"
          @scroll-to-header="scrollToHeader"
          @toggle-step="toggleStep"
          @toggle-header="toggleHeader"
          @delete-map="deleteMap"
          @map-date-change="mapDateChange"
        />
      </template>
    </div>
  </nav>
</template>

<style lang="scss" scoped>
@use "nav/nav-item";

.album-nav {
  --opacity-hidden: 0.45;
  --opacity-toggle-idle: 0.5;
  --opacity-thumb-empty: 0.25;

  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
}

.nav-album-select {
  margin: var(--gap-md) var(--gap-md-lg) 0;
  flex-shrink: 0;
}

.album-select-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg) var(--gap-md);
  flex-shrink: 0;
}

.nav-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;

  &::-webkit-scrollbar {
    width: 0.25rem;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }
}

</style>
