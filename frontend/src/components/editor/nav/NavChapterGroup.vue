<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import { flagUrl } from "@/utils/media";
import NavMapItem from "./NavMapItem.vue";
import NavStepItem from "./NavStepItem.vue";
import { entryKey } from "./useAlbumNavGroups";
import { nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

const props = defineProps<{
  group: ChapterVisit;
  open: boolean;
  activeStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  hiddenHeaderSet: ReadonlySet<string>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
  formatStepDate: (date: Date) => string;
  lazyRoot?: HTMLElement | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  scrollToHeader: [key: string];
  toggleStep: [id: number];
  toggleHeader: [headerKey: HeaderKey];
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

function countryStepCount(stepIds: number[]): string {
  return t("nav.stepCount", stepIds.length);
}

function isRunActive(stepIds: number[]): boolean {
  return props.activeStepId != null && stepIds.includes(props.activeStepId);
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

    <section v-if="open && group.countryRuns.length > 1" class="chapter-route">
      <div class="country-outline">
        <button
          v-for="run in group.countryRuns"
          :key="`${run.code}-${run.firstEntryIndex}`"
          type="button"
          :class="[
            'country-outline-row',
            { 'country-outline-row-active': isRunActive(run.stepIds) },
          ]"
          :style="{ '--country-color': run.color }"
          @click.stop="scrollToEntry(run.firstEntryIndex)"
        >
          <img
            :src="flagUrl(run.code)"
            alt=""
            width="18"
            height="13"
            class="country-flag"
          />
          <span class="country-name" dir="auto">{{ run.name }}</span>
          <span class="country-meta">
            {{ run.dateRange }}
            <span class="country-meta-dot" aria-hidden="true">·</span>
            {{ countryStepCount(run.stepIds) }}
          </span>
        </button>
      </div>
    </section>

    <div
      v-if="open && group.countryRuns.length > 1"
      class="chapter-section-label steps-label"
    >
      {{ t("nav.steps") }}
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
            :active="activeSectionKey === entry.key"
            :steps="steps"
            :colors="colors"
            :format-map-range="formatMapRange"
            @click="emit('scrollToMap', entry.key)"
            @delete="emit('deleteMap', entry.rangeIdx)"
            @date-change="(idx, range) => emit('mapDateChange', idx, range)"
          />
          <NavStepItem
            v-else-if="entry.type === 'step'"
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
          <div
            v-else
            role="button"
            tabindex="0"
            :data-nav-section="entry.key"
            :class="[
              'nav-item',
              'chapter-header-item',
              {
                visible: activeSectionKey === entry.key,
                'nav-hidden': hiddenHeaderSet.has(entry.headerKey),
              },
            ]"
            @click="emit('scrollToHeader', entry.key)"
            @keydown.enter="emit('scrollToHeader', entry.key)"
          >
            <q-icon :name="entry.icon" size="var(--type-sm)" />
            <span>{{ entry.label }}</span>
            <button
              type="button"
              class="chapter-header-toggle"
              :aria-label="
                hiddenHeaderSet.has(entry.headerKey)
                  ? t('nav.showStep')
                  : t('nav.hideStep')
              "
              @click.stop="emit('toggleHeader', entry.headerKey)"
            >
              <q-icon
                :name="
                  hiddenHeaderSet.has(entry.headerKey)
                    ? symOutlinedVisibilityOff
                    : symOutlinedVisibility
                "
                size="var(--type-xs)"
              />
            </button>
          </div>
        </div>
      </template>
    </q-virtual-scroll>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
@use "nav-toggle" as *;

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
  padding: var(--gap-xs) 0 var(--gap-sm);
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-color) 72%, transparent);
}

.chapter-section-label {
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  padding: 0 var(--gap-md-lg) var(--gap-xs);
  color: var(--text-faint);
  font-size: var(--type-xs);
  font-weight: 700;
}

.country-outline {
  display: flex;
  flex-direction: column;
}

.country-outline-row {
  display: grid;
  grid-template-columns: 1.625rem minmax(0, 1fr);
  gap: var(--gap-xs);
  align-items: baseline;
  min-width: 0;
  min-height: 2.125rem;
  padding: var(--gap-xs) var(--gap-md-lg);
  border: 0;
  border-inline-start: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: var(--type-xs);
  text-align: start;
  cursor: pointer;
  transition:
    background var(--duration-fast),
    color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 5%, transparent);
    color: var(--text-bright);
  }
}

.country-outline-row-active {
  border-inline-start-color: var(--country-color);
  background: color-mix(in srgb, var(--country-color) 14%, transparent);
  color: var(--text-bright);
}

.country-flag {
  width: 1.125rem;
  height: 0.8125rem;
  align-self: center;
  border-radius: var(--radius-xs);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--text) 18%, transparent);
  object-fit: cover;
}

.country-name {
  min-width: 0;
  overflow: hidden;
  color: inherit;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.country-meta {
  grid-column: 2;
  min-width: 0;
  overflow: hidden;
  color: var(--text-faint);
  font-size: var(--type-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.country-meta-dot {
  margin: 0 var(--gap-xs);
}

.chapter-entries-virtual {
  max-height: calc(100vh - 18rem);
  overflow-y: auto;
}

.chapter-header-item {
  gap: var(--gap-sm);
  height: 100%;
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);

  > span {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &:hover {
    color: var(--text-bright);
  }

  &.visible {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);
  }
}

.chapter-header-toggle {
  @include nav-toggle(0);

  margin-inline-start: auto;

  .chapter-header-item:hover &,
  .chapter-header-item:focus-within &,
  .chapter-header-item.visible &,
  .chapter-header-item.nav-hidden & {
    opacity: 1;
  }
}

.steps-label {
  padding-top: var(--gap-sm);
  border-top: 1px solid
    color-mix(in srgb, var(--border-color) 72%, transparent);
}

@media (prefers-reduced-motion: reduce) {
  :deep(.chapter-group-header),
  .country-outline-row {
    transition: none;
  }
}
</style>
