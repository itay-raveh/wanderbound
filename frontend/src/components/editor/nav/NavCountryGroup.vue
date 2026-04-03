<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import type { CountryVisit, GroupEntry } from "./types";
import { flagUrl } from "@/utils/media";
import { SHORT_DATE } from "@/utils/date";
import { sectionKeyMatchesRange } from "../../album/albumSections";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
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
  excludedSet: Set<number>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  scrollToStep: [id: number];
  scrollToMap: [dateRange: DateRange];
  toggleStep: [id: number];
  toggleCountry: [];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();

const countryStepIds = computed(() =>
  props.group.entries
    .filter((e): e is Extract<GroupEntry, { type: "step" }> => e.type === "step")
    .map((e) => e.item.id),
);

const allExcluded = computed(() =>
  countryStepIds.value.every((id) => props.excludedSet.has(id)),
);
</script>

<template>
  <q-expansion-item
    :model-value="open"
    dense
    :header-class="['group-header', { 'group-excluded': allExcluded }]"
    expand-icon-class="text-faint"
    :style="{ '--country-color': group.color }"
    @update:model-value="emit('toggleOpen')"
  >
    <template #header>
      <q-item-section avatar class="group-avatar">
        <img :src="flagUrl(group.code)" alt="" width="14" height="10" class="group-flag" />
      </q-item-section>
      <q-item-section class="group-name" dir="auto">{{ group.name }}</q-item-section>
      <q-item-section side :class="['group-dates', 'text-muted', { 'group-dates-excluded': allExcluded }]">
        <span class="group-dates-text">{{ group.dateRange }}</span>
        <button
          type="button"
          class="country-toggle"
          :aria-label="allExcluded ? t('nav.showAll') : t('nav.hideAll')"
          @click.stop="emit('toggleCountry')"
        >
          <q-icon :name="allExcluded ? symOutlinedVisibilityOff : symOutlinedVisibility" size="var(--type-xs)" />
          <q-tooltip>{{ allExcluded ? t("nav.showAll") : t("nav.hideAll") }}</q-tooltip>
        </button>
      </q-item-section>
    </template>

    <template v-for="entry in group.entries" :key="entry.type === 'step' ? entry.item.id : entry.key">
      <NavMapItem
        v-if="entry.type === 'map'"
        :data-nav-section="entry.key"
        :date-range="entry.dateRange"
        :range-idx="entry.rangeIdx"
        :entry-key="entry.key"
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
        :date="formatDate(entry.item.date, SHORT_DATE)"
        :thumb="entry.item.thumb"
        :color="entry.item.color"
        :active="activeStepId === entry.item.id"
        :excluded="excludedSet.has(entry.item.id)"
        @click="emit('scrollToStep', entry.item.id)"
        @toggle="emit('toggleStep', entry.item.id)"
      />
    </template>
  </q-expansion-item>
</template>

<style lang="scss" scoped>
.group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 0.0625rem solid var(--border-color);
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

  .group-excluded & {
    opacity: var(--opacity-excluded);
  }
}

.group-excluded .group-flag {
  opacity: var(--opacity-excluded);
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
  .group-dates-excluded & {
    opacity: 0;
  }
}

.country-toggle {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  opacity: 0;
  transition: opacity var(--duration-fast), color var(--duration-fast), background var(--duration-fast);

  .group-header:hover &,
  .group-dates-excluded & {
    opacity: 1;
  }

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

@media (hover: none) {
  .country-toggle {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .country-toggle {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .group-header,
  .group-flag,
  .group-name,
  .group-dates-text,
  .country-toggle {
    transition: none;
  }
}
</style>
