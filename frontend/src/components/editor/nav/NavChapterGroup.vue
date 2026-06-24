<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, CountryVisit } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import NavCountryGroup from "./NavCountryGroup.vue";
import { useI18n } from "vue-i18n";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineProps<{
  group: ChapterVisit;
  open: boolean;
  openCountryKey: string | null;
  activeStepId: number | null;
  activeSectionKey: string | null;
  hiddenSet: ReadonlySet<number>;
  hiddenHeaderSet: ReadonlySet<string>;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
  lazyRoot?: HTMLElement | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  toggleCountryOpen: [countryKey: string];
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  scrollToHeader: [key: string];
  toggleStep: [id: number];
  toggleHeader: [headerKey: HeaderKey];
  toggleCountry: [country: CountryVisit];
  deleteMap: [rangeIdx: number];
  mapDateChange: [rangeIdx: number, range: DateRange];
}>();
</script>

<template>
  <q-expansion-item
    dense
    :model-value="open"
    header-class="chapter-group-header"
    expand-icon-class="text-faint"
    @update:model-value="emit('toggleOpen')"
  >
    <template #header>
      <q-item-section class="chapter-group-name" dir="auto">
        {{ group.name }}
      </q-item-section>
      <q-item-section side class="chapter-count text-muted">
        {{ group.stepIds.length }}
      </q-item-section>
    </template>

    <div v-if="open" class="header-items">
      <div
        v-for="item in group.headerItems"
        :key="item.key"
        role="button"
        tabindex="0"
        :data-nav-section="item.key"
        :class="[
          'nav-item',
          'header-item',
          {
            visible: activeSectionKey === item.key,
            'nav-hidden': hiddenHeaderSet.has(item.headerKey),
          },
        ]"
        @click="emit('scrollToHeader', item.key)"
        @keydown.enter="emit('scrollToHeader', item.key)"
      >
        <q-icon :name="item.icon" size="var(--type-sm)" />
        <span>{{ item.label }}</span>
        <button
          type="button"
          class="header-toggle"
          :aria-label="
            hiddenHeaderSet.has(item.headerKey) ? t('nav.showStep') : t('nav.hideStep')
          "
          @click.stop="emit('toggleHeader', item.headerKey)"
        >
          <q-icon
            :name="
              hiddenHeaderSet.has(item.headerKey)
                ? symOutlinedVisibilityOff
                : symOutlinedVisibility
            "
            size="var(--type-xs)"
          />
        </button>
      </div>
    </div>

    <NavCountryGroup
      v-for="country in group.countries"
      :key="country.key"
      :group="country"
      :open="openCountryKey === country.key"
      :active-step-id="activeStepId"
      :active-section-key="activeSectionKey"
      :hidden-set="hiddenSet"
      :steps="steps"
      :colors="colors"
      :format-map-range="formatMapRange"
      :lazy-root="lazyRoot ?? null"
      @toggle-open="emit('toggleCountryOpen', country.key)"
      @scroll-to-step="emit('scrollToStep', $event)"
      @scroll-to-map="emit('scrollToMap', $event)"
      @toggle-step="emit('toggleStep', $event)"
      @toggle-country="emit('toggleCountry', country)"
      @delete-map="emit('deleteMap', $event)"
      @map-date-change="(idx, range) => emit('mapDateChange', idx, range)"
    />
  </q-expansion-item>
</template>

<style lang="scss" scoped>
@use "nav-toggle" as *;

.chapter-group-header {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border-top: 1px solid var(--border-color);
  transition: background var(--duration-fast);

  .q-expansion-item:first-child & {
    border-top: none;
  }

  .q-expansion-item--expanded & {
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }
}

.chapter-group-name {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: var(--type-xs);
  font-weight: 700;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.chapter-count {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

.header-items {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.header-item {
  gap: var(--gap-sm);
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-muted);

  > span {
    flex: 1;
  }

  &:hover {
    color: var(--text-bright);
  }

  &.visible {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    border-inline-start-color: var(--q-primary);

    &:hover {
      background: color-mix(in srgb, var(--q-primary) 18%, transparent);
    }

    &:active {
      background: color-mix(in srgb, var(--q-primary) 24%, transparent);
    }
  }
}

.header-toggle {
  @include nav-toggle;

  .header-item:hover & {
    opacity: 1;
  }

  .header-item.nav-hidden & {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .chapter-group-header,
  .header-item {
    transition: none;
  }
}
</style>
