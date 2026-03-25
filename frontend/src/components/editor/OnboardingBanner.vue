<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import {
  symOutlinedEditNote,
  symOutlinedSwapHoriz,
  symOutlinedSettings,
  symOutlinedPictureAsPdf,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { ref } from "vue";

const STORAGE_KEY = "onboarding-editor-dismissed";
const printMode = usePrintMode();
const { t } = useI18n();

const dismissed = ref(localStorage.getItem(STORAGE_KEY) === "1");

function dismiss() {
  dismissed.value = true;
  localStorage.setItem(STORAGE_KEY, "1");
}

const chips = [
  { icon: symOutlinedEditNote, key: "onboarding.editText" },
  { icon: symOutlinedSwapHoriz, key: "onboarding.dragPhotos" },
  { icon: symOutlinedSettings, key: "onboarding.settings" },
  { icon: symOutlinedPictureAsPdf, key: "onboarding.exportPdf" },
] as const;
</script>

<template>
  <Transition name="fade">
    <div v-if="!dismissed && !printMode" class="onboarding-banner fade-up">
      <span class="banner-title text-weight-semibold text-bright">{{ t("onboarding.editorTitle") }}</span>
      <div class="chips row no-wrap items-center">
        <div v-for="chip in chips" :key="chip.key" class="chip row no-wrap items-center">
          <q-icon :name="chip.icon" size="1rem" />
          <span>{{ t(chip.key) }}</span>
        </div>
      </div>
      <q-btn flat dense no-caps class="got-it" @click="dismiss">{{ t("onboarding.gotIt") }}</q-btn>
    </div>
  </Transition>
</template>

<style lang="scss" scoped>
.onboarding-banner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gap-md-lg) var(--gap-lg);
  background: color-mix(in srgb, var(--q-primary) 12%, var(--surface));
  border-bottom: 1px solid color-mix(in srgb, var(--q-primary) 25%, transparent);
}

.banner-title {
  font-size: var(--type-sm);
  white-space: nowrap;
  color: var(--q-primary);
}

.chips {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  gap: var(--gap-sm-md);
  justify-content: center;
}

.chip {
  gap: var(--gap-sm);
  padding: var(--gap-xs) var(--gap-md);
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--q-primary) 18%, transparent);
  color: var(--q-primary);
  font-size: var(--type-xs);
  font-weight: 600;
  white-space: nowrap;
}

.got-it {
  font-weight: 600;
  color: var(--q-primary);
}
</style>
