<script lang="ts" setup>
import { useI18n } from "vue-i18n";

const show = defineModel<boolean>({ required: true });

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();
</script>

<template>
  <q-dialog v-model="show">
    <q-card class="onboarding-card">
      <h3 class="onboarding-title text-weight-semibold text-bright">
        {{ t("upgrade.onboarding.title") }}
      </h3>

      <p class="onboarding-body text-body2 text-muted">
        {{ t("upgrade.onboarding.body") }}
      </p>

      <p class="onboarding-tip text-body2 text-faint">
        {{ t("upgrade.onboarding.tip") }}
      </p>

      <div class="onboarding-actions row no-wrap q-gutter-x-sm">
        <q-btn
          v-close-popup
          flat
          no-caps
          class="col text-body2 cancel-btn"
        >
          {{ t("upgrade.onboarding.cancel") }}
        </q-btn>
        <q-btn
          flat
          no-caps
          class="col text-body2 confirm-btn"
          @click="$emit('confirm')"
        >
          {{ t("upgrade.onboarding.continue") }}
        </q-btn>
      </div>
    </q-card>
  </q-dialog>
</template>

<style lang="scss" scoped>
.onboarding-card {
  padding: 1.75rem;
  max-width: 24rem;
}

.onboarding-title {
  font-size: var(--type-subtitle);
  margin: 0 0 var(--gap-md);
  text-align: center;
}

.onboarding-body {
  line-height: 1.5;
  text-align: center;
  margin: 0 0 var(--gap-md);
}

.onboarding-tip {
  font-size: var(--type-xs);
  text-align: center;
  margin: 0 0 var(--gap-lg);
}

.onboarding-actions {
  margin-top: var(--gap-md);
}

.cancel-btn {
  border: 1px solid var(--border-color);
}

.confirm-btn {
  background: var(--q-primary);
  color: white;
}
</style>
