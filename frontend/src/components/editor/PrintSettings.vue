<script setup lang="ts">
import type { AlbumChapter, AlbumMeta } from "@/client";
import { zAlbumChapter, zAlbumMeta } from "@/client/zod.gen";
import { z } from "zod";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
const props = defineProps<{
  album: AlbumMeta;
  chapter?: AlbumChapter;
  coverOnly?: boolean;
}>();
const { t } = useI18n();
const mutation = useAlbumMutation(() => props.album.id);
const numberInput = z.union([
  z.number(),
  z.string().trim().min(1).pipe(z.coerce.number()),
]);

function dimension(field: z.ZodDefault<z.ZodOptional<z.ZodNumber>>) {
  const schema = field.unwrap().unwrap();
  const { minimum, maximum, type } = z.toJSONSchema(schema);
  return {
    schema: numberInput.pipe(schema),
    minimum,
    maximum,
    integer: type === "integer",
  };
}

const dimensions = {
  safe_margin_mm: dimension(zAlbumMeta.shape.safe_margin_mm),
  interior_bleed_mm: dimension(zAlbumMeta.shape.interior_bleed_mm),
  cover_bleed_mm: dimension(zAlbumMeta.shape.cover_bleed_mm),
  spine_width_mm: dimension(zAlbumChapter.shape.spine_width_mm),
};

function dimensionRule(field: keyof typeof dimensions) {
  const { schema, maximum, integer } = dimensions[field];
  return (raw: unknown) =>
    schema.safeParse(raw).success ||
    t(integer ? "print.wholeDimensionRange" : "print.dimensionRange", {
      max: maximum,
    });
}

function setDimension(
  field: "safe_margin_mm" | "interior_bleed_mm" | "cover_bleed_mm",
  raw: string | number | null,
) {
  const result = dimensions[field].schema.safeParse(raw);
  if (result.success) mutation.mutate({ [field]: result.data });
}

function setSpine(raw: string | number | null) {
  if (!props.chapter) return;
  const result = dimensions.spine_width_mm.schema.safeParse(raw);
  if (!result.success) return;
  mutation.mutate({
    chapters: props.album.chapters?.map((item) =>
      item.id === props.chapter?.id
        ? { ...item, spine_width_mm: result.data }
        : item,
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
      :min="dimensions.safe_margin_mm.minimum"
      :rules="[dimensionRule('safe_margin_mm')]"
      :max="dimensions.safe_margin_mm.maximum"
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
      :min="dimensions.interior_bleed_mm.minimum"
      :rules="[dimensionRule('interior_bleed_mm')]"
      :max="dimensions.interior_bleed_mm.maximum"
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
      :min="dimensions.cover_bleed_mm.minimum"
      :rules="[dimensionRule('cover_bleed_mm')]"
      :max="dimensions.cover_bleed_mm.maximum"
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
        :min="dimensions.spine_width_mm.minimum"
        :rules="[dimensionRule('spine_width_mm')]"
        :max="dimensions.spine_width_mm.maximum"
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
