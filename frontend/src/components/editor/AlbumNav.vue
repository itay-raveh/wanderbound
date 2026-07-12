<script lang="ts" setup>
import { chapterCanSplit } from "./nav/chapterEditing";
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
  openChapterKey,
  formatMapRange,
  boundaryOptions,
  onMapsRangesChange,
  toggleStep,
  toggleHeader,
  toggleChapter,
  onSplitChapter,
  onDeleteChapter,
  onAdjustChapterBoundary,
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
      <template v-for="(group, index) in chapterGroups" :key="group.key">
        <NavChapterGroup
          :group="group"
          :open="openChapterKey === group.key"
          :active-step-id="activeStepId"
          :active-section-key="activeSectionKey"
          :hidden-set="hiddenSet"
          :hidden-header-set="hiddenHeaderSet"
          :steps="steps"
          :colors="albumColors"
          :format-map-range="formatMapRange"
          :lazy-root="listRef ?? null"
          :can-delete="chapterGroups.length > 1"
          :can-split="chapterCanSplit(group.chapter)"
          :merge-target="index === 0 ? 'next' : 'previous'"
          :start-step-id="group.chapter.step_ids?.[0] ?? null"
          :start-options="
            index > 0
              ? boundaryOptions(chapterGroups[index - 1].chapter, group.chapter)
              : []
          "
          @toggle-open="toggleChapter(group)"
          @split-chapter="onSplitChapter(group.chapter.id)"
          @delete-chapter="onDeleteChapter(group.chapter.id)"
          @adjust-boundary="
            onAdjustChapterBoundary(
              chapterGroups[index - 1].chapter.id,
              group.chapter.id,
              $event,
            )
          "
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
