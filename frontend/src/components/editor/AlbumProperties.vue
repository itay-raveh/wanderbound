<script lang="ts" setup>
import type { Album } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { ALLOWED_FONTS, DEFAULT_BODY_FONT, DEFAULT_FONT, fontStack } from "@/utils/fonts";
import { symOutlinedCropFree, symOutlinedTune } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed } from "vue";

const { t } = useI18n();

const props = defineProps<{
  album: Album;
}>();

const albumMutation = useAlbumMutation(() => props.album.id);

const currentFont = computed(() => props.album.font ?? DEFAULT_FONT);
const currentBodyFont = computed(() => props.album.body_font ?? DEFAULT_BODY_FONT);
const safeMargin = computed(() => props.album.safe_margin_mm ?? 0);

function updateFont(font: string) {
  albumMutation.mutate({ font });
}

function updateBodyFont(font: string) {
  albumMutation.mutate({ body_font: font });
}

function updateSafeMargin(mm: number) {
  albumMutation.mutate({ safe_margin_mm: mm });
}
</script>

<template>
  <div class="album-properties">
    <div class="properties-header row no-wrap items-center text-bright">
      <q-icon :name="symOutlinedTune" size="var(--type-md)" />
      <span>{{ t('editor.properties') }}</span>
    </div>
    <q-select
      :model-value="currentFont"
      :options="ALLOWED_FONTS"
      :label="t('editor.font')"
      dense
      borderless
      options-dense
      class="font-picker"
      @update:model-value="updateFont"
    >
      <template #selected>
        <span :style="{ fontFamily: fontStack(currentFont) }">{{ currentFont }}</span>
      </template>
      <template #option="{ itemProps, opt }">
        <q-item v-bind="itemProps" :style="{ fontFamily: fontStack(opt) }">
          <q-item-section>{{ opt }}</q-item-section>
        </q-item>
      </template>
    </q-select>
    <q-select
      :model-value="currentBodyFont"
      :options="ALLOWED_FONTS"
      :label="t('editor.bodyFont')"
      dense
      borderless
      options-dense
      class="font-picker"
      @update:model-value="updateBodyFont"
    >
      <template #selected>
        <span :style="{ fontFamily: fontStack(currentBodyFont) }">{{ currentBodyFont }}</span>
      </template>
      <template #option="{ itemProps, opt }">
        <q-item v-bind="itemProps" :style="{ fontFamily: fontStack(opt) }">
          <q-item-section>{{ opt }}</q-item-section>
        </q-item>
      </template>
    </q-select>
    <div class="margin-group">
      <div class="margin-header row no-wrap items-center">
        <q-icon :name="symOutlinedCropFree" size="var(--type-sm)" class="text-muted" />
        <span class="margin-title text-muted">{{ t('editor.safeMargin') }}</span>
        <span class="margin-label text-muted">{{ safeMargin }}mm</span>
      </div>
      <q-slider
        :model-value="safeMargin"
        :min="0"
        :max="15"
        :step="1"
        snap
        :aria-label="t('editor.safeMargin')"
        @change="updateSafeMargin"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.album-properties {
  display: flex;
  flex-direction: column;
  gap: var(--gap-md-lg);
  flex-shrink: 0;
  padding: var(--gap-md-lg) var(--gap-lg);
}

.properties-header {
  gap: var(--gap-sm);
  font-size: var(--type-sm);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
}

.font-picker {
  background: color-mix(in srgb, var(--text) 5%, transparent);
  border-bottom: 1px solid var(--text-faint);
  border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  padding-inline: var(--gap-sm);
  transition: border-color var(--duration-fast);

  &:hover {
    border-color: var(--text-muted);
  }

  &:focus-within {
    border-color: var(--q-primary);
  }
}

.margin-group {
  padding-inline: var(--gap-xs);
}

.margin-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-xs);
}

.margin-title {
  font-size: var(--type-xs);
  flex: 1;
}

.margin-label {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .font-picker {
    transition: none;
  }
}
</style>
