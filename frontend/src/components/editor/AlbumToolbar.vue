<script lang="ts" setup>
import type { Album, AlbumUpdate, Step } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUserQuery } from "@/queries/useUserQuery";
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { useUndoStack } from "@/composables/useUndoStack";
import { KEY_LABELS } from "@/composables/shortcutKeys";
import { parseLocalDate, SHORT_DATE, toIso, toQDate } from "@/utils/date";
import StepDatePicker from "./StepDatePicker.vue";
import ShortcutsPopup from "./ShortcutsPopup.vue";

import {
  symOutlinedCalendarMonth,
  symOutlinedFlightTakeoff,
  symOutlinedKeyboard,
  symOutlinedPictureAsPdf,
  symOutlinedRedo,
  symOutlinedUndo,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed, ref, watch } from "vue";

const { t } = useI18n();

const props = defineProps<{
  albumIds: string[];
  album?: Album;
  allSteps?: Step[];
}>();

const albumId = defineModel<string | null>("albumId");

const albumMutation = useAlbumMutation(() => props.album?.id ?? "");
const { formatDateRange } = useUserQuery();
const pdf = usePdfExportStream(() => props.album?.id ?? "");
const pdfBusy = computed(() => pdf.state.value !== "idle" && pdf.state.value !== "error");
const undoStack = useUndoStack();

function save(patch: AlbumUpdate) {
  if (!props.album) return;
  albumMutation.mutate(patch);
}

const albumOptions = computed(() =>
  props.albumIds.map((value) => ({ label: toTitleCase(value), value })),
);

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );

function onExportPdf() {
  if (!props.album) return;
  pdf.start();
}

type QDateRange = { from: string; to: string };

const albumColors = computed(() => (props.album?.colors ?? {}) as Record<string, string>);

const dateRangeModel = computed(() => {
  const ranges = props.album?.steps_ranges;
  if (!ranges?.length) return undefined;
  return ranges.map(([from, to]) => ({ from: toQDate(from), to: toQDate(to) }));
});

/** Local draft while the picker is open - only persisted on popup close. */
const draft = ref<(QDateRange | string)[] | QDateRange | string | null>(null);
const pickerOpen = ref(false);

watch(dateRangeModel, (v) => { if (!pickerOpen.value) draft.value = v ?? null; });

function onPickerOpen() {
  draft.value = dateRangeModel.value ?? null;
  pickerOpen.value = true;
}

function onPickerClose() {
  pickerOpen.value = false;
  const val = draft.value;
  if (!val) {
    save({ steps_ranges: [] });
    return;
  }
  const entries = Array.isArray(val) ? val : [val];
  const ranges: [string, string][] = entries.map((e) => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  save({ steps_ranges: ranges.sort(([a], [b]) => a.localeCompare(b)) });
}

const rangeDisplay = computed(() => {
  const ranges = props.album?.steps_ranges;
  if (!ranges?.length) return "";
  return ranges
    .map(([from, to]) =>
      formatDateRange(parseLocalDate(from), parseLocalDate(to), SHORT_DATE),
    )
    .join(", ");
});
</script>

<template>
  <div class="album-toolbar row no-wrap items-center">
    <!-- Navigation & filter controls -->
    <div class="toolbar-group row no-wrap items-center q-gutter-x-sm">
      <q-select
        v-model="albumId"
        :options="albumOptions"
        :aria-label="t('nav.selectAlbum')"
        class="compact-field toolbar-field"
        dense
        outlined
        options-dense
        emit-value
        map-options
      >
        <template #prepend>
          <q-icon :name="symOutlinedFlightTakeoff" size="1.125rem" class="rtl-flip" />
        </template>
      </q-select>

      <q-input
        v-if="album && allSteps?.length"
        :model-value="rangeDisplay"
        :placeholder="t('album.allDates')"
        :aria-label="t('nav.dateFilter')"
        dir="auto"
        class="compact-field toolbar-field"
        dense
        outlined
        readonly
      >
        <template #prepend>
          <q-icon :name="symOutlinedCalendarMonth" size="1rem" class="cursor-pointer">
            <q-popup-proxy transition-show="scale" transition-hide="scale" @before-show="onPickerOpen" @before-hide="onPickerClose">
              <StepDatePicker
                v-model="draft"
                :steps="allSteps!"
                :colors="albumColors"
                range
                multiple
              />
            </q-popup-proxy>
          </q-icon>
        </template>
      </q-input>
    </div>

    <div class="toolbar-spacer" />

    <!-- Editing actions -->
    <div v-if="album" class="toolbar-actions row no-wrap items-center">
      <q-btn class="action-btn" flat dense round :icon="symOutlinedUndo" :disable="!undoStack.canUndo.value" :aria-label="t('shortcuts.undo')" @click="undoStack.undo()">
        <q-tooltip>{{ KEY_LABELS.undo }}</q-tooltip>
      </q-btn>
      <q-btn class="action-btn" flat dense round :icon="symOutlinedRedo" :disable="!undoStack.canRedo.value" :aria-label="t('shortcuts.redo')" @click="undoStack.redo()">
        <q-tooltip>{{ KEY_LABELS.redo }}</q-tooltip>
      </q-btn>
      <q-separator vertical class="action-divider" />
      <q-btn class="util-btn" flat dense round :icon="symOutlinedKeyboard" :aria-label="t('shortcuts.title')">
        <q-tooltip>{{ t("shortcuts.title") }}</q-tooltip>
        <q-popup-proxy transition-show="scale" transition-hide="scale">
          <ShortcutsPopup />
        </q-popup-proxy>
      </q-btn>
      <q-separator vertical class="action-divider" />
      <q-btn
        color="primary"
        unelevated
        no-caps
        dense
        :disable="pdfBusy"
        :aria-busy="pdfBusy"
        @click="onExportPdf"
      >
        <q-icon :name="symOutlinedPictureAsPdf" size="1.25rem" class="q-mr-xs" />
        {{ t("editor.exportPdf") }}
      </q-btn>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.album-toolbar {
  gap: var(--gap-lg);
}

.toolbar-spacer {
  flex: 1;
}

.toolbar-field {
  width: 18rem;
}

.toolbar-actions {
  gap: var(--gap-xs);
}

.action-btn {
  color: var(--text-bright);

  :deep(.q-focus-helper) {
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    opacity: 1;
  }

  &:hover :deep(.q-focus-helper) {
    background: color-mix(in srgb, var(--q-primary) 22%, transparent);
  }

  &.disabled {
    color: var(--text-faint);

    :deep(.q-focus-helper) {
      opacity: 0;
    }
  }
}

.util-btn {
  color: var(--text-faint);
  transition: color var(--duration-fast);

  &:hover {
    color: var(--text-muted);
  }
}

.action-divider {
  margin-inline: var(--gap-sm);
  opacity: 0.5;
}

@media (prefers-reduced-motion: reduce) {
  .util-btn {
    transition: none;
  }
}
</style>
