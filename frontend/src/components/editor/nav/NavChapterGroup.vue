<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import { flagUrl } from "@/utils/media";
import NavMapItem from "./NavMapItem.vue";
import NavStepItem from "./NavStepItem.vue";
import { entryKey } from "./useAlbumNavGroups";
import { nextTick, ref, watch } from "vue";

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
}>();

const emit = defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [range: DateRange];
  toggleStep: [id: number];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();

const NAV_ENTRY_ROW_SIZE = 54;
const NAV_ENTRY_SLICE_SIZE = 24;

type VirtualScrollExpose = {
  scrollTo: (index: number) => void;
  $el?: HTMLElement;
};

const virtualScrollRef = ref<VirtualScrollExpose | null>(null);

function centerVirtualIndex(index: number) {
  virtualScrollRef.value?.scrollTo(index);
  void nextTick(() => {
    requestAnimationFrame(() => {
      const scrollEl = virtualScrollRef.value?.$el;
      if (!scrollEl) return;
      scrollEl.scrollTop = Math.max(
        0,
        index * NAV_ENTRY_ROW_SIZE -
          (scrollEl.clientHeight - NAV_ENTRY_ROW_SIZE) / 2,
      );
    });
  });
}

function scrollToEntry(index: number) {
  centerVirtualIndex(index);
}

function scrollActiveIntoVirtualView() {
  if (!props.open || props.activeStepId == null) return;
  const index = props.group.entryIndexByStepId.get(props.activeStepId);
  if (index == null) return;
  centerVirtualIndex(index);
}

function rowKey(entry: GroupEntry): string {
  return entryKey(entry);
}

watch(
  () => [props.open, props.activeStepId, props.group.entries] as const,
  scrollActiveIntoVirtualView,
  { flush: "post" },
);
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

    <div v-if="open && group.countryRuns.length > 1" class="country-jumps">
      <button
        v-for="run in group.countryRuns"
        :key="`${run.code}-${run.firstEntryIndex}`"
        type="button"
        class="country-jump"
        :style="{ '--country-color': run.color }"
        @click.stop="scrollToEntry(run.firstEntryIndex)"
      >
        <img
          :src="flagUrl(run.code)"
          alt=""
          width="14"
          height="10"
          class="country-jump-flag"
        />
        <span class="country-jump-name" dir="auto">{{ run.name }}</span>
        <span class="country-jump-dates">{{ run.dateRange }}</span>
      </button>
    </div>

    <q-virtual-scroll
      v-if="open"
      ref="virtualScrollRef"
      :items="group.entries"
      class="chapter-entries-virtual"
      :virtual-scroll-item-size="NAV_ENTRY_ROW_SIZE"
      :virtual-scroll-slice-size="NAV_ENTRY_SLICE_SIZE"
    >
      <template #default="{ item: entry }">
        <div :key="rowKey(entry)" class="nav-virtual-row">
          <NavMapItem
            v-if="entry.type === 'map'"
            :data-nav-section="entry.key"
            :date-range="entry.dateRange"
            :range-idx="entry.rangeIdx"
            :active="sectionKeyMatchesRange(activeSectionKey, entry.dateRange)"
            :steps="steps"
            :colors="colors"
            :format-map-range="formatMapRange"
            @click="emit('scrollToMap', entry.dateRange)"
            @delete="emit('deleteMap', entry.rangeIdx)"
            @date-change="(idx, range) => emit('mapDateChange', idx, range)"
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
            @click="emit('scrollToStep', entry.item.id)"
            @toggle="emit('toggleStep', entry.item.id)"
          />
        </div>
      </template>
    </q-virtual-scroll>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
:deep(.chapter-group-header) {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  transition: background var(--duration-fast);

  .q-expansion-item--expanded & {
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }
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

.country-jumps {
  display: flex;
  gap: var(--gap-xs);
  padding: var(--gap-xs) var(--gap-md-lg) var(--gap-sm);
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;
}

.country-jump {
  display: inline-flex;
  align-items: center;
  gap: var(--gap-xs);
  min-width: 0;
  max-width: 12rem;
  padding: 0.1875rem var(--gap-xs);
  border: 1px solid color-mix(in srgb, var(--country-color) 44%, transparent);
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--country-color) 16%, transparent);
  color: var(--text-muted);
  font-size: var(--type-xs);
  cursor: pointer;
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast),
    color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--country-color) 24%, transparent);
    border-color: color-mix(in srgb, var(--country-color) 64%, transparent);
    color: var(--text-bright);
  }
}

.country-jump-flag {
  width: 0.875rem;
  height: 0.625rem;
  flex: 0 0 auto;
  border-radius: var(--radius-xs);
}

.country-jump-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

.country-jump-dates {
  flex: 0 0 auto;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}

.chapter-entries-virtual {
  max-height: calc(100vh - 15rem);
  overflow-y: auto;
}

@media (prefers-reduced-motion: reduce) {
  :deep(.chapter-group-header),
  .country-jump {
    transition: none;
  }
}
</style>
