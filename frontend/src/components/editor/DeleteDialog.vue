<script lang="ts" setup>
import { matDeleteOutline } from "@quasar/extras/material-icons";
import { useI18n } from "vue-i18n";
import ConfirmDialog from "./ConfirmDialog.vue";

const show = defineModel<boolean>({ required: true });

defineProps<{
  deleting: boolean;
}>();

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();
</script>

<template>
  <ConfirmDialog
    v-model="show"
    :icon="matDeleteOutline"
    :title="t('delete.title')"
    :body="t('delete.body')"
    :confirm-label="deleting ? t('delete.deleting') : t('delete.confirm')"
    :cancel-label="t('common.cancel')"
    :confirm-disabled="deleting"
    @confirm="$emit('confirm')"
  />
</template>
