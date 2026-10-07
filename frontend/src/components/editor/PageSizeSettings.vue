<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { AlbumMeta } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { MM_PER_INCH, PAGE_PRESETS, validatePageSize } from "@/utils/pageSize";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";

const props = defineProps<{ album: AlbumMeta }>();
const { t } = useI18n();
const mutation = useAlbumMutation(() => props.album.id);
const unit = ref<"mm" | "in">("mm");
const unitOptions: { label: string; value: "mm" | "in" }[] = [
  { label: "mm", value: "mm" },
  { label: "in", value: "in" },
];
const locked = ref(false);
const saving = ref(false);
const widthMm = ref(297);
const heightMm = ref(210);
const presetId = ref("a4");
const valid = computed(() =>
  validatePageSize({ widthMm: widthMm.value, heightMm: heightMm.value }),
);
const changed = computed(
  () =>
    widthMm.value !== (props.album.page_width_mm ?? 297) ||
    heightMm.value !== (props.album.page_height_mm ?? 210),
);
const options = computed(() => [
  ...PAGE_PRESETS.map((preset) => ({ label: preset.label, value: preset.id })),
  { label: t("print.customSize"), value: "custom" },
]);
const factor = computed(() => (unit.value === "in" ? MM_PER_INCH : 1));
function display(mm: number) {
  return Number.isFinite(mm) ? Number((mm / factor.value).toFixed(6)) : "";
}
function reset() {
  widthMm.value = props.album.page_width_mm ?? 297;
  heightMm.value = props.album.page_height_mm ?? 210;
  presetId.value =
    PAGE_PRESETS.find(
      (preset) =>
        preset.widthMm === widthMm.value && preset.heightMm === heightMm.value,
    )?.id ?? "custom";
}
watch(
  () => [props.album.id, props.album.page_width_mm, props.album.page_height_mm],
  reset,
  { immediate: true },
);
function selectPreset(id: string) {
  presetId.value = id;
  const preset = PAGE_PRESETS.find((item) => item.id === id);
  if (preset) {
    widthMm.value = preset.widthMm;
    heightMm.value = preset.heightMm;
  }
}
function edit(field: "width" | "height", raw: string | number | null) {
  const value =
    raw === null || String(raw).trim() === ""
      ? NaN
      : Number(raw) * factor.value;
  const ratio = widthMm.value / heightMm.value;
  if (field === "width") {
    widthMm.value = value;
    if (locked.value && Number.isFinite(ratio)) heightMm.value = value / ratio;
  } else {
    heightMm.value = value;
    if (locked.value && Number.isFinite(ratio)) widthMm.value = value * ratio;
  }
  presetId.value = "custom";
}
async function apply() {
  if (!valid.value || !changed.value || saving.value) return;
  saving.value = true;
  try {
    await mutation.mutateAsync({
      page_width_mm: widthMm.value,
      page_height_mm: heightMm.value,
    });
  } catch {
    // The shared mutation restores the saved album and reports the failure.
    reset();
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="page-size-settings">
    <div class="size-heading">
      <span>{{ t("print.pageSize") }}</span>
      <SegmentedControl
        v-model="unit"
        :options="unitOptions"
        :aria-label="t('print.dimensionUnits')"
        compact
      />
    </div>
    <q-select
      :model-value="presetId"
      :options="options"
      :label="t('print.sizePreset')"
      emit-value
      map-options
      outlined
      dense
      hide-bottom-space
      :disable="saving"
      @update:model-value="selectPreset"
    />
    <div class="size-dimensions">
      <q-input
        :model-value="display(widthMm)"
        :label="t('print.pageWidth')"
        type="number"
        step="any"
        outlined
        dense
        hide-bottom-space
        :disable="saving"
        @update:model-value="edit('width', $event)"
      />
      <q-input
        :model-value="display(heightMm)"
        :label="t('print.pageHeight')"
        type="number"
        step="any"
        outlined
        dense
        hide-bottom-space
        :disable="saving"
        @update:model-value="edit('height', $event)"
      />
    </div>
    <q-checkbox
      v-model="locked"
      :label="t('print.lockRatio')"
      dense
      :disable="saving"
    />
    <p v-if="!valid" class="size-error" role="alert">
      {{ t("print.pageSizeBounds") }}
    </p>
    <p v-else class="size-note">{{ t("print.pageSizeNote") }}</p>
    <div v-if="changed" class="size-actions">
      <q-btn
        flat
        dense
        no-caps
        :label="t('common.cancel')"
        :disable="saving"
        @click="reset"
      />
      <q-btn
        color="primary"
        dense
        no-caps
        :label="t('print.applySize')"
        :disable="!valid"
        :loading="saving"
        @click="apply"
      />
    </div>
  </div>
</template>

<style scoped>
.page-size-settings {
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
}
.size-heading,
.size-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-md);
}
.size-dimensions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--gap-md);
}
.size-dimensions :deep(input) {
  direction: ltr;
  text-align: left;
}
.size-note,
.size-error {
  margin: 0;
  font-size: var(--type-sm);
  color: var(--text-muted);
}
.size-error {
  color: var(--q-negative);
}
.size-actions {
  justify-content: flex-end;
}
</style>
