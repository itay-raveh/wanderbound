<script lang="ts" setup>
import { symOutlinedHighQuality } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import ConfirmDialog from "./ConfirmDialog.vue";
import { computed } from "vue";

const show = defineModel<boolean>({ required: true });

const props = defineProps<{
  matched: number;
  total: number;
  unmatched: number;
  alreadyUpgraded: number;
}>();

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();

const titleText = computed(() =>
  t("upgrade.summary.title", {
    matched: props.matched,
    total: props.total,
  }),
);

const toUpgrade = computed(() => props.matched - props.alreadyUpgraded);

const bodyText = computed(() => {
  const parts: string[] = [];
  if (props.alreadyUpgraded > 0) {
    parts.push(t("upgrade.summary.alreadyUpgraded", { count: props.alreadyUpgraded }));
  }
  if (props.unmatched > 0) {
    parts.push(t("upgrade.summary.unmatched", { count: props.unmatched }));
  }
  return parts.join(" ");
});
</script>

<template>
  <ConfirmDialog
    v-model="show"
    :icon="symOutlinedHighQuality"
    variant="primary"
    :title="titleText"
    :body="bodyText"
    :confirm-label="t('upgrade.summary.confirm', { count: toUpgrade })"
    :cancel-label="t('upgrade.summary.cancel')"
    @confirm="$emit('confirm')"
  />
</template>
