<script lang="ts" setup>
import {
  symOutlinedPhotoLibrary,
  symOutlinedSwapHoriz,
  symOutlinedHighQuality,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const show = defineModel<boolean>({ required: true });

defineEmits<{
  confirm: [];
}>();

const { t } = useI18n();

const steps = [
  { icon: symOutlinedPhotoLibrary, key: "upgrade.onboarding.step1" },
  { icon: symOutlinedSwapHoriz, key: "upgrade.onboarding.step2" },
  { icon: symOutlinedHighQuality, key: "upgrade.onboarding.step3" },
] as const;
</script>

<template>
  <q-dialog v-model="show">
    <q-card class="onboarding-card">
      <h3 class="onboarding-title text-weight-semibold text-bright">
        {{ t("upgrade.onboarding.title") }}
      </h3>

      <div class="onboarding-steps">
        <div v-for="step in steps" :key="step.key" class="onboarding-step">
          <div class="step-icon flex flex-center">
            <q-icon :name="step.icon" size="1.25rem" />
          </div>
          <p class="step-text text-body2 text-muted">{{ t(step.key) }}</p>
        </div>
      </div>

      <p class="onboarding-tip text-body2 text-faint">
        {{ t("upgrade.onboarding.tip") }}
      </p>

      <div class="onboarding-actions row no-wrap q-gutter-x-sm">
        <q-btn
          v-close-popup
          flat
          no-caps
          class="col text-body2 bg-surface"
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
  max-width: 26rem;
}

.onboarding-title {
  font-size: var(--type-subtitle);
  margin: 0 0 var(--gap-lg);
  text-align: center;
}

.onboarding-steps {
  display: flex;
  flex-direction: column;
  gap: var(--gap-md-lg);
  margin-bottom: var(--gap-lg);
}

.onboarding-step {
  display: flex;
  align-items: flex-start;
  gap: var(--gap-md);
}

.step-icon {
  flex-shrink: 0;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--q-primary) 12%, var(--surface));
  color: var(--q-primary);
}

.step-text {
  margin: 0;
  line-height: 1.5;
  padding-top: 0.25rem;
}

.onboarding-tip {
  font-size: var(--type-xs);
  margin: 0 0 var(--gap-lg);
  padding-inline-start: 3.25rem;
}

.onboarding-actions {
  margin-top: var(--gap-md);
}

.confirm-btn {
  background: var(--q-primary);
  color: white;
}
</style>
