<script lang="ts" setup>
import {
  symOutlinedRoute,
  symOutlinedOpenWith,
  symOutlinedCalendarMonth,
} from "@quasar/extras/material-symbols-outlined";
import { useEditorHints } from "@/composables/useEditorHints";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const { mapBannerDismissed, dismissMapBanner } = useEditorHints();

const chips = [
  { icon: symOutlinedRoute, key: "onboarding.hikesDetected" },
  { icon: symOutlinedOpenWith, key: "onboarding.dragHandles" },
  { icon: symOutlinedCalendarMonth, key: "onboarding.filterDates" },
] as const;
</script>

<template>
  <Transition name="fade">
    <div v-if="!mapBannerDismissed" role="status" class="map-onboarding fade-up">
      <span class="banner-title text-weight-semibold text-bright">{{ t("onboarding.mapTitle") }}</span>
      <div class="chips row no-wrap items-center">
        <div v-for="chip in chips" :key="chip.key" class="chip row no-wrap items-center">
          <q-icon :name="chip.icon" size="1rem" />
          <span>{{ t(chip.key) }}</span>
        </div>
      </div>
      <q-btn flat dense no-caps class="got-it" :aria-label="t('onboarding.gotIt')" @click="dismissMapBanner">{{ t("onboarding.gotIt") }}</q-btn>
    </div>
  </Transition>
</template>

<style lang="scss" scoped>
.map-onboarding {
  display: flex;
  align-items: center;
  gap: var(--gap-lg);
  padding: var(--gap-md) var(--gap-lg);
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  width: calc(var(--page-width) * var(--editor-zoom));
  margin: 0 auto var(--gap-md-lg);
  box-sizing: border-box;
}

.banner-title {
  font-size: var(--type-sm);
  white-space: nowrap;
  flex-shrink: 0;
}

.chips {
  gap: var(--gap-sm-md);
  flex: 1;
  min-width: 0;
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
