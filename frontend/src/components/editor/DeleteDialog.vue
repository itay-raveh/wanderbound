<script lang="ts" setup>
import { matDeleteOutline } from "@quasar/extras/material-icons";
import { useI18n } from "vue-i18n";

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
  <q-dialog v-model="show">
    <q-card class="confirm-dialog text-center">
      <div class="confirm-icon flex flex-center text-danger">
        <q-icon :name="matDeleteOutline" size="1.5rem" />
      </div>
      <h3 class="confirm-title text-weight-semibold text-bright">{{ t("delete.title") }}</h3>
      <p class="confirm-text text-body2 text-muted">{{ t("delete.body") }}</p>
      <div class="confirm-actions row no-wrap q-gutter-x-sm">
        <q-btn v-close-popup flat no-caps class="col text-body2 bg-surface">{{ t("delete.cancel") }}</q-btn>
        <q-btn
          flat
          no-caps
          :disable="deleting"
          class="col text-body2 bg-danger text-white"
          @click="$emit('confirm')"
        >
          {{ deleting ? t("delete.deleting") : t("delete.confirm") }}
        </q-btn>
      </div>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.confirm-dialog {
  padding: 1.75rem;
  max-width: 22rem;
}

.confirm-icon {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--danger) 15%, var(--surface));
  margin: 0 auto var(--gap-lg);
}

.confirm-title {
  font-size: var(--type-subtitle);
  margin: 0 0 var(--gap-md);
}

.confirm-text {
  line-height: 1.5;
  margin: 0 0 var(--gap-lg);
}

</style>
