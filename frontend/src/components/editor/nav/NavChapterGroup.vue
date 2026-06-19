<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit } from "./types";
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

defineEmits<{
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

function scrollActiveIntoVirtualView() {
  if (!props.open || props.activeStepId == null) return;
  const index = props.group.entryIndexByStepId.get(props.activeStepId);
  if (index == null) return;
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
      <q-item-section class="chapter-group-main">
        <span class="chapter-group-name" dir="auto">{{ group.name }}</span>
      </q-item-section>
      <q-item-section side class="chapter-count text-muted">
        {{ group.stepIds.length }}
      </q-item-section>
    </template>

    <q-virtual-scroll
      v-if="open"
      ref="virtualScrollRef"
      :items="group.entries"
      class="chapter-entries-virtual"
      :virtual-scroll-item-size="NAV_ENTRY_ROW_SIZE"
      :virtual-scroll-slice-size="NAV_ENTRY_SLICE_SIZE"
    >
      <template #default="{ item: entry }">
        <div :key="entryKey(entry)" class="nav-virtual-row">
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
              (idx: number, range: DateRange) =>
                $emit('mapDateChange', idx, range)
            "
          />
          <NavStepItem
            v-else
            :data-nav-step="entry.item.id"
            :name="entry.item.name"
            :date="formatStepDate(entry.item.date)"
            :meta="entry.item.countryLabel"
            :thumb="entry.item.thumb"
            :color="entry.item.color"
            :active="activeStepId === entry.item.id"
            :hidden="hiddenSet.has(entry.item.id)"
            :lazy-root="lazyRoot ?? null"
            @click="$emit('scrollToStep', entry.item.id)"
            @toggle="$emit('toggleStep', entry.item.id)"
          />
        </div>
      </template>
    </q-virtual-scroll>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
:deep(.chapter-group-header) {
  min-height: 2.625rem;
  padding: var(--gap-sm) var(--gap-md-lg) var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-color) 70%, transparent);
  background: color-mix(in srgb, var(--text) 3%, transparent);

  &:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }
}

.chapter-group-main {
  min-width: 0;
}

.chapter-group-name {
  display: block;
  color: var(--text);
  font-size: var(--type-xs);
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chapter-count {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

:deep(.q-expansion-item__content) {
  padding-block: var(--gap-xs);
}

.chapter-entries-virtual {
  max-height: calc(100vh - 13rem);
  overflow-y: auto;
}
</style>
