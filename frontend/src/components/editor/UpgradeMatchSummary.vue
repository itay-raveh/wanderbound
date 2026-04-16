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

const bodyText = computed(() => {
  if (props.unmatched > 0) {
    return t("upgrade.summary.unmatched", { count: props.unmatched });
  }
  return "";
});
</script>

<template>
  <ConfirmDialog
    v-model="show"
    :icon="symOutlinedHighQuality"
    variant="primary"
    :title="titleText"
    :body="bodyText"
    :confirm-label="t('upgrade.summary.confirm')"
    :cancel-label="t('upgrade.summary.cancel')"
    @confirm="$emit('confirm')"
  />
</template>
