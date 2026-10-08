<script lang="ts" setup>
import type { DateRange } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import { SHORT_DATE } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { nextTick, onMounted, ref, watch } from "vue";
import NavStepItem from "./NavStepItem.vue";
import NavMapItem from "./NavMapItem.vue";

const { formatDate } = useUserQuery();

const props = defineProps<{
  group: ChapterVisit;
  open: boolean;
  activeStepId: number | null;
  expandedStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  formatMapRange: (dr: DateRange) => string;
  lazyRoot?: HTMLElement | null;
}>();

const NAV_ENTRY_ROW_SIZE = 54;
const NAV_ENTRY_SLICE_SIZE = 24;
type VirtualScrollExpose = {
  scrollTo: (index: number, edge?: string) => void;
  $el?: HTMLElement;
};
const virtualScrollRef = ref<VirtualScrollExpose | null>(null);

function entryKey(entry: GroupEntry) {
  return entry.type === "step" ? `step-${entry.item.id}` : entry.key;
}

function scrollActiveIntoVirtualView() {
  if (!props.open || !props.lazyRoot) return;
  const index =
    props.activeStepId != null
      ? props.group.entryIndexByStepId.get(props.activeStepId)
      : props.group.entries.findIndex(
          (entry) =>
            entry.type === "map" && entry.key === props.activeSectionKey,
        );
  if (index == null || index < 0) return;
  virtualScrollRef.value?.scrollTo(index, "center-force");
  void nextTick(() => {
    requestAnimationFrame(() => {
      const scrollEl = props.lazyRoot;
      const row = virtualScrollRef.value?.$el?.querySelector(
        props.activeStepId != null
          ? `[data-nav-step="${props.activeStepId}"]`
          : `[data-nav-section="${props.activeSectionKey}"]`,
      );
      if (!scrollEl || !row) return;
      scrollEl.scrollTop +=
        row.getBoundingClientRect().top -
        scrollEl.getBoundingClientRect().top -
        (scrollEl.clientHeight - row.clientHeight) / 2;
    });
  });
}

watch(
  () =>
    [
      props.open,
      props.activeStepId,
      props.activeSectionKey,
      props.lazyRoot,
      props.group.entries,
    ] as const,
  scrollActiveIntoVirtualView,
  { flush: "post" },
);
onMounted(() => void nextTick(scrollActiveIntoVirtualView));

defineEmits<{
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  toggleStep: [id: number];
  deleteMap: [rangeIdx: number];
  editMap: [rangeIdx: number, range: DateRange];
}>();
</script>

<template>
  <q-virtual-scroll
    ref="virtualScrollRef"
    :items="group.entries"
    :scroll-target="lazyRoot ?? undefined"
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
          :format-map-range="formatMapRange"
          @click="$emit('scrollToMap', entry.key)"
          @delete="$emit('deleteMap', entry.rangeIdx)"
          @edit="(idx, range) => $emit('editMap', idx, range)"
        />
        <NavStepItem
          v-else
          :data-nav-step="entry.item.id"
          :name="entry.item.name"
          :date="formatDate(entry.item.date, SHORT_DATE)"
          :thumb="entry.item.thumb"
          :color="entry.item.color"
          :active="activeStepId === entry.item.id"
          :aria-expanded="expandedStepId === entry.item.id"
          :hidden="hiddenSet.has(entry.item.id)"
          :lazy-root="lazyRoot"
          @click="$emit('scrollToStep', entry.item.id)"
          @toggle="$emit('toggleStep', entry.item.id)"
        />
        <slot
          v-if="
            entry.type === 'step' &&
            expandedStepId === entry.item.id &&
            !hiddenSet.has(entry.item.id)
          "
          name="step-pages"
          :step-id="entry.item.id"
        />
      </div>
    </template>
  </q-virtual-scroll>
</template>

<style lang="scss" scoped>
.chapter-entries-virtual {
  // The sidebar owns scrolling; this list only supplies virtual padding.
  overflow: visible;
  // Quasar maintains the scroll offset as virtual rows are replaced.
  overflow-anchor: none;
}
</style>
