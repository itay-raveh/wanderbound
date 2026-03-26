<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { useEditorHints } from "@/composables/useEditorHints";
import {
  symOutlinedEditNote,
  symOutlinedSwapHoriz,
  symOutlinedSettings,
  symOutlinedPictureAsPdf,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const printMode = usePrintMode();
const { t } = useI18n();
const { bannerDismissed, dismissBanner } = useEditorHints();

const chips = [
  { icon: symOutlinedEditNote, key: "onboarding.editText" },
  { icon: symOutlinedSwapHoriz, key: "onboarding.dragPhotos" },
  { icon: symOutlinedSettings, key: "onboarding.settings" },
  { icon: symOutlinedPictureAsPdf, key: "onboarding.exportPdf" },
] as const;
</script>

<template>
  <Transition name="fade">
    <div v-if="!bannerDismissed && !printMode" role="status" class="onboarding-banner fade-up">
      <span class="banner-title text-weight-semibold">{{ t("onboarding.editorTitle") }}</span>
      <div class="chips row no-wrap items-center">
        <div v-for="chip in chips" :key="chip.key" class="chip row no-wrap items-center">
          <q-icon :name="chip.icon" size="1rem" />
          <span>{{ t(chip.key) }}</span>
        </div>
      </div>
      <q-btn flat dense no-caps class="got-it" :aria-label="t('onboarding.gotIt')" @click="dismissBanner">{{ t("onboarding.gotIt") }}</q-btn>
    </div>
  </Transition>
</template>

<style lang="scss" scoped>
.onboarding-banner {
  display: flex;
  align-items: center;
  gap: var(--gap-lg);
  padding: var(--gap-md-lg) var(--gap-lg);
  background: color-mix(in srgb, var(--q-primary) 12%, var(--surface));
  border-bottom: 1px solid color-mix(in srgb, var(--q-primary) 25%, transparent);
}

.banner-title {
  font-size: var(--type-sm);
  white-space: nowrap;
  flex-shrink: 0;
  color: var(--primary-text);
}

.chips {
  flex: 1;
  min-width: 0;
  gap: var(--gap-sm-md);
  justify-content: center;
  overflow: hidden;
}

.chip {
  gap: var(--gap-sm);
  padding: var(--gap-xs) var(--gap-md);
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--q-primary) 18%, transparent);
  color: var(--primary-text);
  font-size: var(--type-xs);
  font-weight: 600;
  white-space: nowrap;
}

.got-it {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--primary-text);
}
</style>
