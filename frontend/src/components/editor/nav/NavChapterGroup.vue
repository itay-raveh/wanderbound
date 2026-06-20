<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit } from "./types";
import NavMapItem from "./NavMapItem.vue";
import NavStepItem from "./NavStepItem.vue";
import { entryKey } from "./useAlbumNavGroups";

defineProps<{
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
}>();

defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [range: DateRange];
  toggleStep: [id: number];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();
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
    </template>

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
</style>
