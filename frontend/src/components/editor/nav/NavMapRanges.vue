<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import { toQDate } from "@/utils/date";
import {
  useDateRangePicker,
  parseDraftRanges,
} from "@/composables/useDateRangePicker";
import { useUndoStack } from "@/composables/useUndoStack";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { ref, computed, nextTick } from "vue";
import {
  symOutlinedMap,
  symOutlinedKeyboardArrowDown,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const $q = useQuasar();
const undoStack = useUndoStack();

type PopupExpose = { hide: () => void };

const props = defineProps<{
  steps: Step[];
  mapsRanges: DateRange[];
  colors: Record<string, string>;
}>();

const emit = defineEmits<{
  "update:mapsRanges": [ranges: DateRange[]];
}>();

const confirmingClear = ref(false);

const mapRangesModel = computed(() => {
  if (!props.mapsRanges.length) return null;
  return props.mapsRanges.map(([from, to]) => ({
    from: toQDate(from),
    to: toQDate(to),
  }));
});

const { draft, open, close } = useDateRangePicker(() => mapRangesModel.value);

function onPickerOpen() {
  open();
  confirmingClear.value = false;
}

function onPickerClose() {
  const val = close();
  emit("update:mapsRanges", parseDraftRanges(val));
}

const popupRef = ref<PopupExpose>();

function clearAllMaps() {
  draft.value = null;
  confirmingClear.value = false;
  popupRef.value?.hide();
  void nextTick(() => {
    $q.notify({
      message: t("nav.mapsCleared"),
      timeout: 4000,
      actions: [
        {
          label: t("shortcuts.undo"),
          color: "primary",
          handler: () => undoStack.undo(),
        },
      ],
    });
  });
}
</script>

<template>
  <button
    type="button"
    class="nav-chip"
    :aria-label="t('nav.mapRanges')"
    aria-haspopup="dialog"
    @click.stop
  >
    <q-icon :name="symOutlinedMap" size="var(--type-xs)" />
    <span>{{ t("nav.maps") }}</span>
    <q-icon
      :name="symOutlinedKeyboardArrowDown"
      size="var(--type-xs)"
      class="chip-chevron"
    />
    <q-popup-proxy
      ref="popupRef"
      transition-show="scale"
      transition-hide="scale"
      @before-show="onPickerOpen"
      @before-hide="onPickerClose"
    >
      <div class="picker-panel">
        <StepDatePicker
          v-model="draft"
          :steps="steps"
          :colors="colors"
          range
          multiple
        />
        <div v-if="mapsRanges.length" class="picker-footer">
          <template v-if="!confirmingClear">
            <button
              type="button"
              class="picker-clear-btn"
              @click="confirmingClear = true"
            >
              {{ t("nav.clear") }}
            </button>
          </template>
          <template v-else>
            <span class="picker-confirm-text">{{
              t("nav.removeAllMaps")
            }}</span>
            <div class="picker-confirm-actions">
              <button
                type="button"
                class="picker-cancel-btn"
                @click="confirmingClear = false"
              >
                {{ t("common.cancel") }}
              </button>
              <button
                type="button"
                class="picker-remove-btn"
                @click="clearAllMaps"
              >
                {{ t("nav.remove") }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </q-popup-proxy>
  </button>
</template>

<style lang="scss" scoped>
@use "picker";

.picker-confirm-text {
  font-size: var(--type-xs);
  color: var(--text-muted);
}

.picker-confirm-actions {
  display: flex;
  gap: var(--gap-sm);
  margin-inline-start: auto;
}

.picker-cancel-btn,
.picker-remove-btn {
  appearance: none;
  border: none;
  font: inherit;
  font-size: var(--type-xs);
  cursor: pointer;
  padding: var(--gap-xs) var(--gap-sm-md);
  border-radius: var(--radius-sm);
  transition: background var(--duration-fast);

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 1px;
  }
}

.picker-cancel-btn {
  background: none;
  color: var(--text-muted);

  &:hover {
    background: color-mix(in srgb, var(--text) 8%, transparent);
  }

  &:active {
    background: color-mix(in srgb, var(--text) 14%, transparent);
  }
}

.picker-remove-btn {
  background: var(--danger);
  color: #fff; // white-on-danger - standard for filled destructive buttons

  &:hover {
    background: color-mix(in srgb, var(--danger) 85%, black);
  }

  &:active {
    background: color-mix(in srgb, var(--danger) 75%, black);
  }
}

@media (prefers-reduced-motion: reduce) {
  .picker-cancel-btn,
  .picker-remove-btn {
    transition: none;
  }
}
</style>
