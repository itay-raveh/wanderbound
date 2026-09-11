<script setup lang="ts">
import type { AlbumChapter, AlbumMeta } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
const props = defineProps<{
  album: AlbumMeta;
  chapter?: AlbumChapter;
  coverOnly?: boolean;
}>();
const { t } = useI18n();
const mutation = useAlbumMutation(() => props.album.id);
function dimensionRule(max: number, integer = false) {
  return (raw: unknown) => {
    const value = Number(raw);
    return (
      (raw !== "" &&
        raw !== null &&
        Number.isFinite(value) &&
        value >= 0 &&
        value <= max &&
        (!integer || Number.isInteger(value))) ||
      t(integer ? "print.wholeDimensionRange" : "print.dimensionRange", { max })
    );
  };
}
function setDimension(
  field: "safe_margin_mm" | "interior_bleed_mm" | "cover_bleed_mm",
  raw: string | number | null,
) {
  if (raw === null || raw === "") return;
  const value = Number(raw);
  const max = field === "safe_margin_mm" ? 15 : 20;
  if (
    !Number.isFinite(value) ||
    value < 0 ||
    value > max ||
    (field === "safe_margin_mm" && !Number.isInteger(value))
  )
    return;
  mutation.mutate({ [field]: value });
}
function setSpine(raw: string | number | null) {
  if (raw === null || raw === "" || !props.chapter) return;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0 || value > 100) return;
  mutation.mutate({
    chapters: props.album.chapters?.map((item) =>
      item.id === props.chapter?.id ? { ...item, spine_width_mm: value } : item,
    ),
  });
}
</script>

<template>
  <div class="print-settings" :class="{ 'cover-controls': coverOnly }">
    <q-input
      v-if="!coverOnly"
      :model-value="album.safe_margin_mm ?? 0"
      :label="t('editor.safeMargin')"
      type="number"
      min="0"
      :rules="[dimensionRule(15, true)]"
      max="15"
      step="1"
      suffix="mm"
      dense
      hide-bottom-space
      outlined
      @update:model-value="setDimension('safe_margin_mm', $event)"
    />
    <q-input
      v-if="!coverOnly"
      :model-value="album.interior_bleed_mm ?? 0"
      :label="t('print.interiorBleed')"
      type="number"
      min="0"
      :rules="[dimensionRule(20)]"
      max="20"
      step="1"
      suffix="mm"
      dense
      hide-bottom-space
      outlined
      @update:model-value="setDimension('interior_bleed_mm', $event)"
    />
    <q-input
      :model-value="album.cover_bleed_mm ?? 0"
      :label="t('print.coverBleed')"
      type="number"
      min="0"
      :rules="[dimensionRule(20)]"
      max="20"
      step="1"
      suffix="mm"
      dense
      hide-bottom-space
      outlined
      @update:model-value="setDimension('cover_bleed_mm', $event)"
    />
    <template v-if="chapter">
      <q-input
        :model-value="chapter.spine_width_mm ?? 0"
        :label="t('print.spineWidth')"
        type="number"
        min="0"
        :rules="[dimensionRule(100)]"
        max="100"
        step="1"
        suffix="mm"
        dense
        hide-bottom-space
        outlined
        @update:model-value="setSpine"
      />
    </template>
  </div>
</template>

<style scoped>
.print-settings {
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
  padding: var(--gap-lg);
}
.cover-controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 0;
}
</style>
