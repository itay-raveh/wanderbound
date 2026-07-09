<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, CountryVisit } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import NavCountryGroup from "./NavCountryGroup.vue";
import { useI18n } from "vue-i18n";
import { ref } from "vue";
import {
  symOutlinedCallSplit,
  symOutlinedDelete,
  symOutlinedMoreVert,
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const menuOpen = ref(false);

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
  canSplit?: boolean;
  startOptions?: { label: string; value: number }[];
  startStepId?: number | null;
}>();

const emit = defineEmits<{
  toggleOpen: [];
  splitChapter: [];
  deleteChapter: [];
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
      <q-item-section side class="chapter-meta-actions text-muted">
        <span class="chapter-date-range">{{ group.dateRange }}</span>
        <q-btn
          type="button"
          dense
          flat
          round
          class="chapter-action"
          :icon="symOutlinedMoreVert"
          :aria-label="t('chapters.actions')"
          @click.stop="menuOpen = true"
        >
          <q-menu v-model="menuOpen" no-parent-event>
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
              <q-separator v-if="startOptions?.length" class="chapter-menu-separator" />
              <q-item
                clickable
                :disable="!canSplit"
                v-close-popup
                class="chapter-menu-action"
                @click="emit('splitChapter')"
              >
                <q-item-section side class="chapter-menu-icon">
                  <q-icon :name="symOutlinedCallSplit" />
                </q-item-section>
                <q-item-section>{{ t("chapters.split") }}</q-item-section>
              </q-item>
              <q-separator class="chapter-menu-separator" />
              <q-item
                clickable
                :disable="!canDelete"
                v-close-popup
                class="chapter-menu-action chapter-menu-danger"
                @click="emit('deleteChapter')"
              >
                <q-item-section side class="chapter-menu-icon">
                  <q-icon :name="symOutlinedDelete" />
                </q-item-section>
                <q-item-section>{{ t("chapters.delete") }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
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

.chapter-meta-actions {
  display: grid;
  min-width: 0;
  flex-shrink: 1;
  overflow: hidden;
  font-size: var(--type-xs);
  white-space: nowrap;

  > * {
    grid-area: 1 / 1;
    justify-self: end;
    align-self: center;
  }
}

.chapter-date-range {
  overflow: hidden;
  max-width: 8rem;
  text-overflow: ellipsis;
  transition: opacity var(--duration-fast);

  .chapter-group-header:hover &,
  .chapter-meta-actions:focus-within & {
    opacity: 0;
  }
}

.chapter-action {
  color: var(--text-muted);
  opacity: 0;
  transition:
    color var(--duration-fast),
    opacity var(--duration-fast);

  .chapter-group-header:hover &,
  .chapter-meta-actions:focus-within & {
    opacity: 1;
  }

  &:hover {
    color: var(--text-bright);
  }
}

.chapter-action-menu {
  min-width: 13.5rem;
  padding: var(--gap-xs);
  color: var(--text-bright);
}

.chapter-start-item {
  min-height: 3.25rem;
  padding: 0 var(--gap-sm);
  border-radius: var(--radius-sm);

  :deep(.q-field__control) {
    min-height: 2.75rem;
    padding-inline: 0;
  }

  :deep(.q-field__label) {
    color: var(--text-muted);
    font-size: var(--type-xs);
    font-weight: 650;
  }

  :deep(.q-field__native) {
    color: var(--text-bright);
    font-size: var(--type-sm);
    font-weight: 600;
  }
}

.chapter-menu-separator {
  margin: var(--gap-xs) 0;
  background: var(--border-color);
}

.chapter-menu-action {
  min-height: 2.5rem;
  padding-inline: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 600;

  &:hover {
    background: color-mix(in srgb, var(--q-primary) 14%, transparent);
  }
}

.chapter-menu-icon {
  min-width: 2rem;
  padding-inline-end: var(--gap-sm);
  color: var(--text-muted);
}

.chapter-menu-danger {
  color: var(--q-negative);

  .chapter-menu-icon {
    color: currentColor;
  }

  &:hover {
    background: color-mix(in srgb, var(--q-negative) 14%, transparent);
  }
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
  .chapter-action,
  .chapter-date-range,
  .header-item {
    transition: none;
  }
}
</style>
