<script lang="ts" setup>
import type { DateRange, StepRead as Step } from "@/client";
import type { ChapterVisit } from "./types";
import type { HeaderKey } from "@/components/album/albumSections";
import { useI18n } from "vue-i18n";
import { ref } from "vue";
import ChapterActionMenu from "./ChapterActionMenu.vue";
import ChapterEntryList from "./ChapterEntryList.vue";
import ChapterHeaderRows from "./ChapterHeaderRows.vue";
import {
  symOutlinedMenuBook,
  symOutlinedMoreVert,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const menuOpen = ref(false);

type StartOption = {
  label: string;
  value: number;
  countryCode: string;
  countryLabel: string;
};

defineProps<{
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
            <ChapterActionMenu
              :can-delete="canDelete"
              :can-split="canSplit"
              :merge-target="mergeTarget"
              :start-options="startOptions"
              :start-step-id="startStepId"
              @adjust-boundary="emit('adjustBoundary', $event)"
              @delete-chapter="emit('deleteChapter')"
              @split-chapter="emit('splitChapter')"
            />
          </q-menu>
        </q-btn>
      </q-item-section>
    </template>

    <ChapterHeaderRows
      v-if="open"
      :group="group"
      :active-section-key="activeSectionKey"
      :hidden-header-set="hiddenHeaderSet"
      @scroll-to-header="emit('scrollToHeader', $event)"
      @toggle-header="emit('toggleHeader', $event)"
    />

    <ChapterEntryList
      v-if="open"
      :group="group"
      :open="open"
      :active-step-id="activeStepId"
      :active-section-key="activeSectionKey"
      :hidden-set="hiddenSet"
      :steps="steps"
      :colors="colors"
      :format-map-range="formatMapRange"
      :lazy-root="lazyRoot"
      @delete-map="emit('deleteMap', $event)"
      @map-date-change="(idx, range) => emit('mapDateChange', idx, range)"
      @scroll-to-map="emit('scrollToMap', $event)"
      @scroll-to-step="emit('scrollToStep', $event)"
      @toggle-step="emit('toggleStep', $event)"
    />
  </q-expansion-item>
</template>

<style lang="scss" scoped>
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

@media (prefers-reduced-motion: reduce) {
  .chapter-group-header,
  .chapter-action,
  .chapter-date-range {
    transition: none;
  }
}
</style>
