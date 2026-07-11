<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit, GroupEntry } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import { SHORT_DATE } from "@/utils/date";
import { flagUrl } from "@/utils/media";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { computed, nextTick, ref, watch } from "vue";
import NavStepItem from "./NavStepItem.vue";
import NavMapItem from "./NavMapItem.vue";
import {
  symOutlinedCallMerge,
  symOutlinedCallSplit,
  symOutlinedMenuBook,
  symOutlinedMoreVert,
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const { formatDate } = useUserQuery();
const menuOpen = ref(false);

type StartOption = {
  label: string;
  value: number;
  countryCode: string;
  countryLabel: string;
};

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
  lazyRoot?: HTMLElement | null;
  canDelete?: boolean;
  canSplit?: boolean;
  mergeTarget?: "previous" | "next";
  startOptions?: StartOption[];
  startStepId?: number | null;
}>();

const selectedStartOption = computed(
  () =>
    props.startOptions?.find((option) => option.value === props.startStepId) ??
    null,
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

const emit = defineEmits<{
  toggleOpen: [];
  splitChapter: [];
  deleteChapter: [];
  adjustBoundary: [firstStepId: number];
  scrollToStep: [id: number];
  scrollToMap: [key: string];
  scrollToHeader: [key: string];
  toggleStep: [id: number];
  toggleHeader: [headerKey: HeaderKey];
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
      <q-item-section avatar class="chapter-group-mark">
        <q-icon :name="symOutlinedMenuBook" size="var(--type-md)" />
      </q-item-section>
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
                    class="chapter-start-select"
                    popup-content-class="chapter-start-popup"
                    dense
                    borderless
                    emit-value
                    map-options
                    options-dense
                    @update:model-value="emit('adjustBoundary', Number($event))"
                  >
                    <template #selected>
                      <div
                        v-if="selectedStartOption"
                        class="chapter-start-selected"
                        dir="ltr"
                      >
                        <img
                          :src="flagUrl(selectedStartOption.countryCode)"
                          :alt="selectedStartOption.countryLabel"
                          class="chapter-start-flag"
                        />
                        <span class="chapter-start-label" dir="auto">
                          {{ selectedStartOption.label }}
                        </span>
                      </div>
                    </template>
                    <template #option="scope">
                      <q-item
                        v-bind="scope.itemProps"
                        class="chapter-start-option"
                        dir="ltr"
                      >
                        <q-item-section side class="chapter-start-option-flag">
                          <img
                            :src="flagUrl(scope.opt.countryCode)"
                            :alt="scope.opt.countryLabel"
                            class="chapter-start-flag"
                          />
                        </q-item-section>
                        <q-item-section class="chapter-start-option-text">
                          <span class="chapter-start-label" dir="auto">
                            {{ scope.opt.label }}
                          </span>
                        </q-item-section>
                      </q-item>
                    </template>
                  </q-select>
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
                class="chapter-menu-action"
                @click="emit('deleteChapter')"
              >
                <q-item-section side class="chapter-menu-icon">
                  <q-icon :name="symOutlinedCallMerge" />
                </q-item-section>
                <q-item-section>
                  {{
                    t(
                      mergeTarget === "next"
                        ? "chapters.mergeNext"
                        : "chapters.mergePrevious",
                    )
                  }}
                </q-item-section>
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
            :active="activeSectionKey === entry.key"
            :color="entry.color"
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
@use "nav-item";
@use "nav-toggle" as *;

:deep(.chapter-group-header) {
  min-height: 3.25rem;
  padding-block: var(--gap-md);
  padding-inline: var(--gap-md-lg);
  border-top: 1px solid color-mix(in srgb, var(--border-color) 72%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 72%, transparent);
  background: color-mix(in srgb, var(--bg-secondary) 48%, transparent);
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast),
    box-shadow var(--duration-fast);
}

:deep(.q-expansion-item:first-child .chapter-group-header) {
  border-top: none;
}

:deep(.q-expansion-item--expanded .chapter-group-header) {
  background: color-mix(in srgb, var(--text) 5%, var(--bg-secondary));
  border-bottom-color: color-mix(in srgb, var(--text-muted) 34%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-bright) 5%, transparent);
}

.chapter-group-mark {
  min-width: 1.5rem;
  padding-inline-end: var(--gap-xs);
  color: color-mix(in srgb, var(--text-muted) 78%, transparent);

  :deep(.q-icon) {
    display: block;
  }

  .q-expansion-item--expanded & {
    color: var(--text-bright);
  }
}

.chapter-group-name {
  min-width: 0;
  overflow: hidden;
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 700;
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

  :deep(.chapter-group-header:hover) &,
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

  :deep(.chapter-group-header:hover) &,
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

.chapter-start-select {
  min-width: 0;
}

.chapter-start-selected,
:global(.chapter-start-option) {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  min-width: 0;
  text-align: left;
}

.chapter-start-selected {
  width: 100%;
}

.chapter-start-flag {
  width: 0.875rem;
  height: 0.625rem;
  flex: 0 0 auto;
  border-radius: var(--radius-xs);
}

.chapter-start-label {
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.chapter-start-popup) {
  direction: ltr;
  text-align: left;
}

:global(.chapter-start-option) {
  min-height: 2.25rem;
  padding-inline: var(--gap-sm);
}

:global(.chapter-start-option-flag) {
  min-width: unset;
  padding-inline-end: 0;
}

:global(.chapter-start-option-text) {
  min-width: 0;
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

.header-items {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.chapter-entries-virtual {
  max-height: calc(100vh - 13rem);
  overflow-y: auto;
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
