<script lang="ts" setup>
import { usePhotoUpgrade } from "@/composables/usePhotoUpgrade";
import ProgressBar from "@/components/ui/ProgressBar.vue";
import UpgradeOnboardingDialog from "./UpgradeOnboardingDialog.vue";
import UpgradeMatchSummary from "./UpgradeMatchSummary.vue";
import {
  symOutlinedClose,
  symOutlinedCheck,
  symOutlinedUpgrade,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed } from "vue";

const { t } = useI18n();

const props = defineProps<{ albumId: string }>();

const upgrade = usePhotoUpgrade();

const isRunning = computed(() => {
  const p = upgrade.phase.value;
  return (
    p === "authorizing" ||
    p === "picking" ||
    p === "matching" ||
    p === "downloading"
  );
});

const progressFraction = computed(() => {
  const { done, total } = upgrade.progress.value;
  if (total === 0) return 0;
  return done / total;
});

const progressMessage = computed(() => {
  const p = upgrade.phase.value;
  const { done, total } = upgrade.progress.value;
  switch (p) {
    case "authorizing":
      return t("upgrade.authorizing");
    case "picking":
      return t("upgrade.picking");
    case "matching":
      return t("upgrade.matching", { done, total });
    case "downloading":
      return t("upgrade.downloading", { done, total });
    default:
      return "";
  }
});

const showOnboarding = computed({
  get: () => upgrade.phase.value === "onboarding",
  set: (v: boolean) => {
    if (!v) upgrade.cancel();
  },
});

const showSummary = computed({
  get: () => upgrade.phase.value === "confirming",
  set: (v: boolean) => {
    if (!v) upgrade.cancel();
  },
});

const { confirmUpgrade } = upgrade;
</script>

<template>
  <template v-if="upgrade.googlePhotosState.value !== 'unavailable'">
    <button
      v-if="upgrade.phase.value === 'done'"
      class="export-btn done"
      aria-disabled="true"
      :aria-label="t('upgrade.done', { count: upgrade.matchSummary.value?.matched ?? 0 })"
    >
      <q-icon
        :name="symOutlinedCheck"
        size="var(--type-lg)"
        class="done-icon"
      />
      {{ t("upgrade.done", { count: upgrade.matchSummary.value?.matched ?? 0 }) }}
    </button>

    <button
      v-else-if="isRunning"
      class="export-btn running"
      :aria-label="progressMessage"
      aria-busy="true"
      @click="upgrade.cancel()"
    >
      <div class="progress-content">
        <q-icon
          :name="symOutlinedClose"
          size="var(--type-md)"
          class="cancel-icon"
        />
        <span class="progress-text" aria-live="polite">{{
          progressMessage
        }}</span>
      </div>
      <ProgressBar :progress="progressFraction" />
    </button>

    <button
      v-else
      class="export-btn"
      :aria-label="t('upgrade.button')"
      @click="upgrade.start(props.albumId)"
    >
      <q-icon :name="symOutlinedUpgrade" size="var(--type-lg)" />
      {{ t("upgrade.button") }}
    </button>

    <UpgradeOnboardingDialog
      v-model="showOnboarding"
      @confirm="confirmUpgrade"
    />

    <UpgradeMatchSummary
      v-model="showSummary"
      :matched="upgrade.matchSummary.value?.matched ?? 0"
      :total="upgrade.matchSummary.value?.totalMedia ?? 0"
      :unmatched="upgrade.matchSummary.value?.unmatched ?? 0"
      @confirm="confirmUpgrade"
    />
  </template>
</template>

<style lang="scss" scoped>
@use "@/styles/action-button" as *;
@include action-button;
</style>
