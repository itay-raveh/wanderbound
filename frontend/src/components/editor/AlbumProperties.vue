<script lang="ts" setup>
import type { AlbumMedia, AlbumMeta } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import {
  ALLOWED_FONTS,
  DEFAULT_BODY_FONT,
  DEFAULT_FONT,
  fontStack,
} from "@/utils/fonts";
import { useI18n } from "vue-i18n";
import { computed } from "vue";

const { t } = useI18n();

const props = defineProps<{
  album: AlbumMeta;
  media: AlbumMedia[];
}>();

const albumMutation = useAlbumMutation(() => props.album.id);

const currentFont = computed(() => props.album.font ?? DEFAULT_FONT);
const currentBodyFont = computed(
  () => props.album.body_font ?? DEFAULT_BODY_FONT,
);

function updateFont(font: string) {
  albumMutation.mutate({ font });
}

function updateBodyFont(font: string) {
  albumMutation.mutate({ body_font: font });
}
</script>

<template>
  <div class="album-properties">
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
        <span :style="{ fontFamily: fontStack(currentFont) }">{{
          currentFont
        }}</span>
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
        <span :style="{ fontFamily: fontStack(currentBodyFont) }">{{
          currentBodyFont
        }}</span>
      </template>
      <template #option="{ itemProps, opt }">
        <q-item v-bind="itemProps" :style="{ fontFamily: fontStack(opt) }">
          <q-item-section>{{ opt }}</q-item-section>
        </q-item>
      </template>
    </q-select>
    <q-toggle
      :model-value="album.show_page_numbers ?? false"
      :label="t('editor.showPageNumbers')"
      dense
      @update:model-value="albumMutation.mutate({ show_page_numbers: $event })"
    />
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

@media (prefers-reduced-motion: reduce) {
  .font-picker {
    transition: none;
  }
}
</style>
