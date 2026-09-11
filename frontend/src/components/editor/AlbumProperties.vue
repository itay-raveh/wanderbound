<script lang="ts" setup>
import type { AlbumMedia, AlbumMeta } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUserQuery } from "@/queries/useUserQuery";
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
const { countryName } = useUserQuery();
const saving = computed(() => albumMutation.asyncStatus.value === "loading");
const colors = computed(() => props.album.colors as Record<string, string>);

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

function updateColor(code: string, color: string | null) {
  if (!color || !/^#[\da-f]{6}$/i.test(color)) return;
  const value = color.toLowerCase();
  if (value === colors.value[code]?.toLowerCase()) return;
  albumMutation.mutate({ colors: { ...colors.value, [code]: value } });
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
    <div v-if="Object.keys(colors).length" class="accent-colors">
      <span class="color-label">{{ t("editor.accentColors") }}</span>
      <q-btn
        v-for="(color, code) in colors"
        :key="code"
        flat
        no-caps
        class="country-color"
        :aria-label="`${countryName(code, code)} · ${t('editor.accentColors')}`"
      >
        <span class="country-name">{{ countryName(code, code) }}</span>
        <span
          class="color-swatch"
          :style="{ backgroundColor: color }"
          aria-hidden="true"
        />
        <q-popup-proxy :aria-label="countryName(code, code)">
          <q-color
            :model-value="color"
            format-model="hex"
            :disable="saving"
            @change="updateColor(code, $event)"
          />
        </q-popup-proxy>
      </q-btn>
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

.accent-colors {
  display: flex;
  flex-direction: column;
}

.color-label {
  color: var(--text-muted);
  font-size: var(--type-xs);
  margin-block-end: var(--gap-sm);
}

.country-color {
  padding: var(--gap-sm) var(--gap-sm);
  min-height: 2.5rem;
  color: var(--text);

  :deep(.q-btn__content) {
    width: 100%;
    gap: var(--gap-md);
    justify-content: space-between;
    flex-wrap: nowrap;
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.country-name {
  text-align: start;
}

.color-swatch {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

@media (prefers-reduced-motion: reduce) {
  .font-picker {
    transition: none;
  }
}
</style>
