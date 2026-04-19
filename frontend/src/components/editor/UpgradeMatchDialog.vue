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
  newThisRound: number;
}>();

defineEmits<{
  confirm: [];
  selectMore: [];
}>();

const { t } = useI18n();

const toUpgrade = computed(() => props.matched - props.alreadyUpgraded);

const titleText = computed(() => {
  if (props.matched === 0) return t("upgrade.summary.noMatchTitle");
  if (props.newThisRound === 0 && props.matched > 0)
    return t("upgrade.summary.noNewMatchTitle");
  if (toUpgrade.value === 0) return t("upgrade.summary.allUpgradedTitle");
  return t("upgrade.summary.readyTitle", { count: toUpgrade.value });
});

const bodyText = computed(() => {
  if (props.matched === 0) return t("upgrade.summary.noMatchBody");
  if (props.newThisRound === 0 && props.matched > 0)
    return t("upgrade.summary.noNewMatchBody");
  if (toUpgrade.value === 0) return t("upgrade.summary.allUpgradedBody");
  if (props.alreadyUpgraded > 0)
    return t("upgrade.summary.alreadyUpgraded", {
      count: props.alreadyUpgraded,
    });
  return "";
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
    :cancel-label="t('common.cancel')"
    :secondary-label="t('upgrade.summary.selectMore')"
    @confirm="$emit('confirm')"
    @secondary="$emit('selectMore')"
  />
</template>
