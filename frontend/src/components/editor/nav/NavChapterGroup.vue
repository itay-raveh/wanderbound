<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, CountryVisit } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import NavCountryGroup from "./NavCountryGroup.vue";
import { useI18n } from "vue-i18n";
import {
  symOutlinedArrowDownward,
  symOutlinedArrowUpward,
  symOutlinedDelete,
  symOutlinedMoreVert,
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
  canDelete?: boolean;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  startOptions?: { label: string; value: number }[];
  startStepId?: number | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  deleteChapter: [];
  moveChapter: [direction: -1 | 1];
  adjustBoundary: [firstStepId: number];
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
      <q-item-section side class="chapter-actions">
        <q-btn
          type="button"
          dense
          flat
          round
          class="chapter-action"
          :icon="symOutlinedMoreVert"
          :aria-label="t('chapters.actions')"
          @click.stop
        >
          <q-menu>
            <q-list dense class="chapter-action-menu">
              <q-item v-if="startOptions?.length" class="chapter-start-item">
                <q-item-section>
                  <q-select
                    :model-value="startStepId"
                    :options="startOptions"
                    :label="t('chapters.startsAt')"
                    dense
                    borderless
                    emit-value
                    map-options
                    options-dense
                    @update:model-value="emit('adjustBoundary', Number($event))"
                  />
                </q-item-section>
              </q-item>
              <q-item
                clickable
                :disable="!canMoveUp"
                v-close-popup
                @click="emit('moveChapter', -1)"
              >
                <q-item-section side>
                  <q-icon :name="symOutlinedArrowUpward" />
                </q-item-section>
                <q-item-section>{{ t("chapters.moveUp") }}</q-item-section>
              </q-item>
              <q-item
                clickable
                :disable="!canMoveDown"
                v-close-popup
                @click="emit('moveChapter', 1)"
              >
                <q-item-section side>
                  <q-icon :name="symOutlinedArrowDownward" />
                </q-item-section>
                <q-item-section>{{ t("chapters.moveDown") }}</q-item-section>
              </q-item>
              <q-item
                clickable
                :disable="!canDelete"
                v-close-popup
                @click="emit('deleteChapter')"
              >
                <q-item-section side>
                  <q-icon :name="symOutlinedDelete" />
                </q-item-section>
                <q-item-section>{{ t("chapters.delete") }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
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
@use "nav-item";
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
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chapter-actions {
  display: flex;
  flex-direction: row;
  gap: var(--gap-xs);
  opacity: 0;
  transition: opacity var(--duration-fast);

  .chapter-group-header:hover &,
  .q-expansion-item--expanded &,
  &:focus-within {
    opacity: 1;
  }
}

.chapter-action {
  color: var(--text-muted);

  &:hover {
    color: var(--text-bright);
  }
}

.chapter-action-menu {
  min-width: 12rem;
}

.chapter-start-item {
  padding-block: var(--gap-xs);
  min-height: 3rem;
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
  .chapter-actions,
  .header-item {
    transition: none;
  }
}
</style>
