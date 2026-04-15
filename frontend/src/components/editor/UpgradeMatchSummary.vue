<script lang="ts" setup>
import { symOutlinedHighQuality } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const show = defineModel<boolean>({ required: true });

defineProps<{
  matched: number;
  total: number;
  unmatched: number;
}>();

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();
</script>

<template>
  <q-dialog v-model="show">
    <q-card class="summary-card text-center">
      <div class="summary-icon flex flex-center">
        <q-icon :name="symOutlinedHighQuality" size="1.5rem" />
      </div>

      <h3 class="summary-title text-weight-semibold text-bright">
        {{ t("upgrade.summary.title") }}
      </h3>

      <p class="summary-matched text-body2 text-muted">
        {{ t("upgrade.summary.matched", { matched, total }) }}
      </p>

      <p v-if="unmatched > 0" class="summary-unmatched text-body2 text-faint">
        {{ t("upgrade.summary.unmatched", { count: unmatched }) }}
      </p>

      <div class="summary-actions row no-wrap q-gutter-x-sm">
        <q-btn
          v-close-popup
          flat
          no-caps
          class="col text-body2 bg-surface"
        >
          {{ t("upgrade.summary.cancel") }}
        </q-btn>
        <q-btn
          flat
          no-caps
          class="col text-body2 confirm-btn"
          @click="$emit('confirm')"
        >
          {{ t("upgrade.summary.confirm") }}
        </q-btn>
      </div>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.summary-card {
  padding: 1.75rem;
  max-width: 22rem;
}

.summary-icon {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  margin: 0 auto var(--gap-lg);
  background: color-mix(in srgb, var(--q-primary) 12%, var(--surface));
  color: var(--q-primary);
}

.summary-title {
  font-size: var(--type-subtitle);
  margin: 0 0 var(--gap-md);
}

.summary-matched {
  line-height: 1.5;
  margin: 0 0 var(--gap-xs);
}

.summary-unmatched {
  font-size: var(--type-xs);
  margin: 0 0 var(--gap-lg);
}

.summary-actions {
  margin-top: var(--gap-lg);
}

.confirm-btn {
  background: var(--q-primary);
  color: white;
}
</style>
