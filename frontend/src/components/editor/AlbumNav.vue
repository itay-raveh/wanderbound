<script lang="ts" setup>
import type { DateRange } from "@/client";
import type { AlbumNavProps } from "./nav/types";
import { inDateRange, isoDate } from "@/utils/date";
import { rangeSectionKey } from "@/components/album/albumSections";
import { useAlbumNavScrollSync } from "./nav/useAlbumNavScrollSync";
import { useAlbumNavModel } from "./nav/useAlbumNavModel";
import { nextTick, ref } from "vue";
import NavMapRanges from "./nav/NavMapRanges.vue";
import MapRangeDialog from "./nav/MapRangeDialog.vue";
import NavChapterGroup from "./nav/NavChapterGroup.vue";
import { symOutlinedFlightTakeoff } from "@quasar/extras/material-symbols-outlined";

const props = withDefaults(defineProps<AlbumNavProps>(), {
  albumIds: () => [],
  hiddenSteps: () => [],
  hiddenHeaders: () => [],
  colors: () => ({}),
  mapsRanges: () => [],
});

const selectedAlbumId = defineModel<string | null>("albumId");

const listRef = ref<HTMLElement>();
const {
  t,
  albumOptions,
  hiddenSet,
  hiddenHeaderSet,
  chapterGroups,
  chapterRows,
  openChapterKey,
  formatMapRange,
  toggleStep,
  toggleHeader,
  toggleChapter,
  onSplitChapter,
  onDeleteChapter,
  onAdjustChapterBoundaryFromRow,
  deleteMap,
  addMap,
  replaceMap,
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

const mapDialogOpen = ref(false);
const editingMap = ref<{ rangeIdx: number; dateRange: DateRange } | null>(null);
const mapStatus = ref("");

function openAddMap() {
  editingMap.value = null;
  mapDialogOpen.value = true;
}

function openEditMap(rangeIdx: number, dateRange: DateRange) {
  editingMap.value = { rangeIdx, dateRange };
  mapDialogOpen.value = true;
}

async function saveMap(range: DateRange) {
  const isEditing = editingMap.value != null;
  if (editingMap.value) replaceMap(editingMap.value.rangeIdx, range);
  else addMap(range);

  const firstStep = props.steps.find((step) =>
    inDateRange(isoDate(step.datetime), range),
  );
  const group = firstStep
    ? chapterGroups.value.find((candidate) =>
        candidate.stepIds.includes(firstStep.id),
      )
    : null;
  if (!group) return;
  mapStatus.value = "";
  await nextTick();
  scrollToMap(rangeSectionKey("map", range, group.chapter));
  mapStatus.value = t(isEditing ? "nav.mapUpdated" : "nav.mapAdded");
}
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
      <NavMapRanges @add-map="openAddMap" />
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
          @edit-map="openEditMap"
        />
      </template>
    </div>

    <MapRangeDialog
      v-model="mapDialogOpen"
      :steps="steps"
      :date-range="editingMap?.dateRange"
      @save="saveMap"
    />
    <span class="sr-only" role="status" aria-live="polite">{{
      mapStatus
    }}</span>
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

.sr-only {
  position: absolute;
  width: 0.0625rem;
  height: 0.0625rem;
  margin: -0.0625rem;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
