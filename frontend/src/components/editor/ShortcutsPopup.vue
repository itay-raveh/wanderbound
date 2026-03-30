<script lang="ts" setup>
import { PHOTO_SHORTCUTS, KEY_LABELS } from "@/composables/shortcutKeys";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const shortcuts = computed(() => [
  { keys: "← →", label: t("shortcuts.navigatePhotos") },
  {
    keys: PHOTO_SHORTCUTS.sendToUnused.toUpperCase(),
    label: t("shortcuts.sendToUnused"),
  },
  {
    keys: PHOTO_SHORTCUTS.setAsCover.toUpperCase(),
    label: t("shortcuts.setAsCover"),
  },
  { keys: "Esc", label: t("shortcuts.clearSelection") },
  { keys: KEY_LABELS.undo, label: t("shortcuts.undo") },
  { keys: KEY_LABELS.redo, label: t("shortcuts.redo") },
]);
</script>

<template>
  <div class="shortcuts-popup q-pa-md">
    <div class="text-subtitle2 text-weight-bold q-mb-sm">
      {{ t("shortcuts.title") }}
    </div>
    <div
      v-for="s in shortcuts"
      :key="s.keys"
      class="shortcut-row row no-wrap items-center q-mb-xs"
    >
      <kbd class="key-badge">{{ s.keys }}</kbd>
      <span class="text-body2 text-muted">{{ s.label }}</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.shortcuts-popup {
  min-width: 14rem;
}

.shortcut-row {
  gap: var(--gap-md);
}

.key-badge {
  display: inline-block;
  min-width: 2.5rem;
  text-align: center;
  padding: var(--gap-xs) var(--gap-sm);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--text) 10%, transparent);
  font-family: var(--font-mono), monospace;
  font-size: var(--type-xs);
  font-weight: 600;
  white-space: nowrap;
}
</style>
