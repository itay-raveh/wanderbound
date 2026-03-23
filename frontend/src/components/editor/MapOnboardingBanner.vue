<script lang="ts" setup>
import {
  symOutlinedRoute,
  symOutlinedOpenWith,
  symOutlinedCalendarMonth,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { ref } from "vue";

const STORAGE_KEY = "onboarding-map-dismissed";
const { t } = useI18n();

const dismissed = ref(localStorage.getItem(STORAGE_KEY) === "1");

function dismiss() {
  dismissed.value = true;
  localStorage.setItem(STORAGE_KEY, "1");
}

const chips = [
  { icon: symOutlinedRoute, key: "onboarding.hikesDetected" },
  { icon: symOutlinedOpenWith, key: "onboarding.dragHandles" },
  { icon: symOutlinedCalendarMonth, key: "onboarding.filterDates" },
] as const;
</script>

<template>
  <Transition name="fade">
    <div v-if="!dismissed" class="map-onboarding fade-up">
      <span class="banner-title text-weight-semibold text-bright">{{ t("onboarding.mapTitle") }}</span>
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
  justify-content: center;
}

.chip {
  gap: var(--gap-sm);
  padding: var(--gap-xs) var(--gap-md);
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  color: var(--q-primary);
  font-size: var(--type-xs);
  font-weight: 500;
  white-space: nowrap;
}

.got-it {
  flex-shrink: 0;
  font-weight: 600;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-normal) ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
