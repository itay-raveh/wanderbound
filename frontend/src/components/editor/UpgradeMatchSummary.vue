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
  selectMore: [];
}>();

const { t } = useI18n();

const toUpgrade = computed(() => props.matched - props.alreadyUpgraded);

const titleText = computed(() => {
  if (props.matched === 0) return t("upgrade.summary.noMatchTitle");
  if (toUpgrade.value === 0) return t("upgrade.summary.allUpgradedTitle");
  return t("upgrade.summary.title", {
    matched: props.matched,
    total: props.total,
  });
});

const bodyText = computed(() => {
  if (props.matched === 0) return t("upgrade.summary.noMatchBody");
  if (toUpgrade.value === 0) return t("upgrade.summary.allUpgradedBody");
  const parts: string[] = [];
  if (props.alreadyUpgraded > 0) {
    parts.push(t("upgrade.summary.alreadyUpgraded", { count: props.alreadyUpgraded }));
  }
  if (props.unmatched > 0) {
    parts.push(t("upgrade.summary.unmatched", { count: props.unmatched }));
  }
  return parts.join("\n");
});

const confirmLabel = computed(() => {
  if (toUpgrade.value <= 0) return undefined;
  return t("upgrade.summary.confirm", { count: toUpgrade.value });
});
</script>

<template>
  <ConfirmDialog
    v-model="show"
    :icon="symOutlinedHighQuality"
    variant="primary"
    :title="titleText"
    :body="bodyText"
    :confirm-label="confirmLabel"
    :cancel-label="t('upgrade.summary.cancel')"
    :secondary-label="t('upgrade.summary.selectMore')"
    @confirm="$emit('confirm')"
    @secondary="$emit('selectMore')"
  />
</template>
