<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import { SHORT_DATE } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { nextTick, ref, watch } from "vue";
import NavStepItem from "./NavStepItem.vue";
import NavMapItem from "./NavMapItem.vue";

const { formatDate } = useUserQuery();

const props = defineProps<{
  group: ChapterVisit;
  open: boolean;
  activeStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
  lazyRoot?: HTMLElement | null;
}>();

const NAV_ENTRY_ROW_SIZE = 54;
const NAV_ENTRY_SLICE_SIZE = 24;
type VirtualScrollExpose = {
  scrollTo: (index: number) => void;
  $el?: HTMLElement;
};
const virtualScrollRef = ref<VirtualScrollExpose | null>(null);

function entryKey(entry: GroupEntry) {
  return entry.type === "step" ? `step-${entry.item.id}` : entry.key;
}

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

defineEmits<{
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  toggleStep: [id: number];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();
</script>

<template>
  <q-virtual-scroll
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
          :active="activeSectionKey === entry.key"
          :color="entry.color"
          :steps="steps"
          :colors="colors"
          :format-map-range="formatMapRange"
          @click="$emit('scrollToMap', entry.key)"
          @delete="$emit('deleteMap', entry.rangeIdx)"
          @date-change="(idx, range) => $emit('mapDateChange', idx, range)"
        />
        <NavStepItem
          v-else
          :data-nav-step="entry.item.id"
          :name="entry.item.name"
          :date="formatDate(entry.item.date, SHORT_DATE)"
          :thumb="entry.item.thumb"
          :color="entry.item.color"
          :active="activeStepId === entry.item.id"
          :hidden="hiddenSet.has(entry.item.id)"
          :lazy-root="lazyRoot"
          @click="$emit('scrollToStep', entry.item.id)"
          @toggle="$emit('toggleStep', entry.item.id)"
        />
      </div>
    </template>
  </q-virtual-scroll>
</template>

<style lang="scss" scoped>
.chapter-entries-virtual {
  max-height: calc(100vh - 13rem);
  overflow-y: auto;
}
</style>
