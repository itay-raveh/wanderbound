<script lang="ts" setup>
import { matWarning } from "@quasar/extras/material-icons";
import { useI18n } from "vue-i18n";
import PromptDialog from "@/components/ui/PromptDialog.vue";
import { computed } from "vue";

const show = defineModel<boolean>({ required: true });

const props = defineProps<{
  caution: number;
  warning: number;
}>();

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();

const bodyText = computed(() => {
  if (props.warning > 0 && props.caution > 0)
    return t("quality.exportBody", {
      warning: props.warning,
      caution: props.caution,
    });
  if (props.warning > 0)
    return t("quality.exportBodyWarningOnly", { warning: props.warning });
  return t("quality.exportBodyCautionOnly", { caution: props.caution });
});
</script>

<template>
  <PromptDialog
    v-model="show"
    :icon="matWarning"
    variant="warning"
    :title="t('quality.exportTitle')"
    :body="bodyText"
    :confirm-label="t('quality.exportConfirm')"
    :cancel-label="t('quality.exportCancel')"
    @confirm="$emit('confirm')"
  />
</template>
