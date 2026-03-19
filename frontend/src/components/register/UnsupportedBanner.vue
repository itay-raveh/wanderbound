<script lang="ts" setup>
import { matWarning } from "@quasar/extras/material-icons";
import { useI18n } from "vue-i18n";

defineProps<{
  reason: string | null;
}>();

const { t } = useI18n();
</script>

<template>
  <div class="banner">
    <div class="banner-header row no-wrap items-center q-gutter-x-sm">
      <q-icon :name="matWarning" size="sm" class="text-danger" />
      <span class="text-subtitle1 text-bright">{{ t("register.unsupportedTitle") }}</span>
    </div>
    <i18n-t keypath="register.unsupportedBody" tag="p" class="text-body2 text-muted no-margin">
      <template #chrome><strong>Chrome</strong></template>
      <template #firefox><strong>Firefox</strong></template>
      <template #safari><strong>Safari</strong></template>
      <template #edge><strong>Edge</strong></template>
    </i18n-t>
    <span v-if="reason" class="text-caption block q-mt-xs text-faint">{{ reason }}</span>
  </div>
</template>

<style scoped>
.banner {
  padding: 1rem 1.25rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 6%, var(--bg-secondary));
}

.banner-header {
  margin-bottom: var(--gap-sm-md);
}

.banner strong {
  color: var(--text);
}
</style>
