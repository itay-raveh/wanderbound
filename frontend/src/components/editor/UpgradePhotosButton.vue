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
      return t("upgrade.onboarding.continue");
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

function onConfirmOnboarding() {
  upgrade.confirmUpgrade();
}

function onConfirmUpgrade() {
  upgrade.confirmUpgrade();
}
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
      @confirm="onConfirmOnboarding"
    />

    <UpgradeMatchSummary
      v-model="showSummary"
      :matched="upgrade.matchSummary.value?.matched ?? 0"
      :total="upgrade.matchSummary.value?.totalPhotos ?? 0"
      :unmatched="upgrade.matchSummary.value?.unmatched ?? 0"
      @confirm="onConfirmUpgrade"
    />
  </template>
</template>

<style lang="scss" scoped>
.export-btn {
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--q-primary);
  border: 1px solid var(--q-primary);
  padding: var(--gap-sm) var(--gap-md-lg);
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  min-height: 2.75rem;
  white-space: nowrap;
  transition:
    background var(--duration-fast),
    color var(--duration-fast),
    border-color var(--duration-fast);

  &:hover:not([aria-disabled]):not(.running) {
    background: var(--q-primary);
    color: var(--bg);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.export-btn.running {
  border-color: var(--border-color);
  color: var(--text-muted);
  cursor: pointer;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: var(--gap-xs);
  min-width: 10rem;

  &:hover {
    border-color: var(--text-faint);

    .cancel-icon {
      color: var(--text);
    }
  }
}

.progress-content {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.cancel-icon {
  color: var(--text-faint);
  transition: color var(--duration-fast);
}

.progress-text {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

.export-btn.done {
  border-color: var(--q-primary);
  color: var(--q-primary);
  cursor: default;
}

.done-icon {
  animation: scale-in var(--duration-normal) cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes scale-in {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .done-icon {
    animation: none;
  }
}
</style>
