<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import NavMapItem from "./NavMapItem.vue";
import NavStepItem from "./NavStepItem.vue";
import { entryKey } from "./useAlbumNavGroups";
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  symOutlinedAltRoute,
  symOutlinedKeyboardArrowDown,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

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
const countrySummary = computed(() => {
  const names = props.group.countryRuns.map((run) => run.name);
  if (names.length <= 3) return names.join(" · ");
  return `${names.slice(0, 3).join(" · ")} · +${names.length - 3}`;
});

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

    <div v-if="open && group.countryRuns.length > 1" class="chapter-route">
      <div class="chapter-route-main">
        <q-icon
          :name="symOutlinedAltRoute"
          size="var(--type-xs)"
          class="chapter-route-icon"
        />
        <span class="chapter-route-label">{{ t("nav.route") }}</span>
        <span class="chapter-route-summary" dir="auto">
          {{ countrySummary }}
        </span>
      </div>
      <button type="button" class="route-menu-button">
        <span>{{ t("nav.jump") }}</span>
        <q-icon :name="symOutlinedKeyboardArrowDown" size="var(--type-xs)" />
        <q-menu class="route-menu" anchor="bottom end" self="top end">
          <q-list dense class="route-menu-list">
            <q-item
              v-for="run in group.countryRuns"
              :key="`${run.code}-${run.firstEntryIndex}`"
              v-close-popup
              clickable
              class="route-menu-item"
              @click="scrollToEntry(run.firstEntryIndex)"
            >
              <q-item-section avatar class="route-menu-marker-wrap">
                <span
                  class="route-menu-marker"
                  :style="{ '--country-color': run.color }"
                />
              </q-item-section>
              <q-item-section>
                <q-item-label dir="auto">{{ run.name }}</q-item-label>
                <q-item-label caption>{{ run.dateRange }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-menu>
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

.chapter-route {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--gap-xs);
  padding: var(--gap-xs) var(--gap-md-lg) var(--gap-sm);
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 72%, transparent);
}

.chapter-route-main {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--gap-xs);
  color: var(--text-muted);
  font-size: var(--type-xs);
}

.chapter-route-icon {
  flex: 0 0 auto;
  color: var(--text-faint);
}

.chapter-route-label {
  flex: 0 0 auto;
  color: var(--text-faint);
  font-weight: 700;
}

.chapter-route-summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-menu-button {
  display: inline-flex;
  align-items: center;
  gap: var(--gap-2xs, 0.25rem);
  min-height: 1.625rem;
  padding: 0 var(--gap-xs);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  cursor: pointer;
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast),
    color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
    border-color: color-mix(in srgb, var(--text) 18%, transparent);
    color: var(--text-bright);
  }
}

.route-menu-list {
  min-width: 12rem;
  max-width: 18rem;
}

.route-menu-item {
  min-height: 2.625rem;
}

.route-menu-marker-wrap {
  min-width: 1rem;
  padding-inline-end: var(--gap-xs);
}

.route-menu-marker {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999rem;
  background: var(--country-color);
}

.chapter-entries-virtual {
  max-height: calc(100vh - 15rem);
  overflow-y: auto;
}

@media (prefers-reduced-motion: reduce) {
  :deep(.chapter-group-header),
  .route-menu-button {
    transition: none;
  }
}
</style>
