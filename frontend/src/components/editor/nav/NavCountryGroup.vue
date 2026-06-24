<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { CountryVisit, GroupEntry } from "./types";
import { flagUrl } from "@/utils/media";
import { SHORT_DATE } from "@/utils/date";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { computed, nextTick, ref, watch } from "vue";
import NavStepItem from "./NavStepItem.vue";
import NavMapItem from "./NavMapItem.vue";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDate } = useUserQuery();

const props = defineProps<{
  group: CountryVisit;
  open: boolean;
  activeStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
  lazyRoot?: HTMLElement | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  toggleStep: [id: number];
  toggleCountry: [];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();

const allHidden = computed(() =>
  props.group.stepIds.every((id) => props.hiddenSet.has(id)),
);

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
</script>

<template>
  <q-expansion-item
    :model-value="open"
    dense
    :header-class="['group-header', { 'group-hidden': allHidden }]"
    expand-icon-class="text-faint"
    :style="{ '--country-color': group.color }"
    @update:model-value="emit('toggleOpen')"
  >
    <template #header>
      <q-item-section avatar class="group-avatar">
        <img
          :src="flagUrl(group.code)"
          alt=""
          width="14"
          height="10"
          class="group-flag"
        />
      </q-item-section>
      <q-item-section class="group-name" dir="auto">{{
        group.name
      }}</q-item-section>
      <q-item-section
        side
        :class="[
          'group-dates',
          'text-muted',
          { 'group-dates-hidden': allHidden },
        ]"
      >
        <span class="group-dates-text">{{ group.dateRange }}</span>
        <button
          type="button"
          class="country-toggle"
          :aria-label="allHidden ? t('nav.showAll') : t('nav.hideAll')"
          @click.stop="emit('toggleCountry')"
        >
          <q-icon
            :name="allHidden ? symOutlinedVisibilityOff : symOutlinedVisibility"
            size="var(--type-xs)"
          />
        </button>
      </q-item-section>
    </template>

    <q-virtual-scroll
      v-if="open"
      ref="virtualScrollRef"
      :items="group.entries"
      class="group-entries-virtual"
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
            :steps="steps"
            :colors="colors"
            :format-map-range="formatMapRange"
            @click="emit('scrollToMap', entry.key)"
            @delete="emit('deleteMap', entry.rangeIdx)"
            @date-change="(idx, range) => emit('mapDateChange', idx, range)"
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
            @click="emit('scrollToStep', entry.item.id)"
            @toggle="emit('toggleStep', entry.item.id)"
          />
        </div>
      </template>
    </q-virtual-scroll>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
@use "nav-toggle" as *;

.group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  transition: background var(--duration-fast);

  .q-expansion-item:first-child & {
    border-top: none;
  }

  .q-expansion-item--expanded & {
    background: color-mix(in srgb, var(--country-color) 15%, transparent);
  }
}

.group-avatar {
  min-width: unset;
  padding-inline-end: var(--gap-sm);
}

.group-flag {
  width: 0.875rem;
  height: 0.625rem;
  border-radius: var(--radius-xs);
  transition: opacity var(--duration-fast);
}

.group-name {
  font-size: var(--type-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--text-muted);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity var(--duration-fast);

  .group-hidden & {
    opacity: var(--opacity-hidden);
  }
}

.group-hidden .group-flag {
  opacity: var(--opacity-hidden);
}

.group-entries-virtual {
  max-height: calc(100vh - 13rem);
  overflow-y: auto;
}

.group-header .group-dates {
  display: grid;
  font-size: var(--type-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex-shrink: 1;

  > * {
    grid-area: 1 / 1;
    justify-self: end;
    align-self: center;
  }
}

.group-dates-text {
  transition: opacity var(--duration-fast);

  .group-header:hover &,
  .group-dates-hidden & {
    opacity: 0;
  }
}

.country-toggle {
  @include nav-toggle(0);

  .group-header:hover &,
  .group-dates-hidden & {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .group-header,
  .group-flag,
  .group-name,
  .group-dates-text {
    transition: none;
  }
}
</style>
