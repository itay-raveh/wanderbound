<script lang="ts" setup>
import { useMediaUpgrade } from "@/composables/useMediaUpgrade";
import type { UpgradeErrorKey } from "@/utils/upgradeErrors";
import { Platform } from "quasar";
import AsyncActionButton from "@/components/ui/AsyncActionButton.vue";
import PromptDialog from "@/components/ui/PromptDialog.vue";
import UpgradeMatchDialog from "./UpgradeMatchDialog.vue";
import {
  symOutlinedError,
  symOutlinedKeyboardArrowDown,
  symOutlinedLinkOff,
  symOutlinedUpgrade,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";

const { t } = useI18n();

const props = defineProps<{ albumId: string }>();

const upgrade = useMediaUpgrade();
const showDisconnectConfirm = ref(false);

const isRunning = computed(() => {
  const p = upgrade.phase.value;
  return (
    p === "authorizing" ||
    p === "picking" ||
    p === "preparing" ||
    p === "matching" ||
    p === "downloading"
  );
});

const buttonState = computed<"idle" | "running" | "done" | null>(() => {
  const p = upgrade.phase.value;
  if (p === "done") return "done";
  if (isRunning.value) return "running";
  if (p === "error") return null;
  if (!Platform.is.chrome) return null;
  if (upgrade.googlePhotosState.value === "connected") return null;
  return "idle";
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
    case "preparing":
      return t("upgrade.preparing", { done, total });
    case "matching":
      return t("upgrade.matching", { done, total });
    case "downloading":
      return t("upgrade.downloading", { done, total });
    default:
      return "";
  }
});

// q-dialog's v-model write fires on both user-dismissal (ESC/backdrop) and
// programmatic hide (phase advanced via confirm). Filter on current phase to
// only treat writes-while-still-in-phase as dismissals.
function onOnboardingVisibility(v: boolean) {
  if (!v && upgrade.phase.value === "onboarding") upgrade.cancel();
}

function onSummaryVisibility(v: boolean) {
  if (!v && upgrade.phase.value === "confirming") upgrade.cancel();
}

const doneMessage = computed(() => {
  const { done: replaced, total, skipped = 0 } = upgrade.progress.value;
  const failed = total - replaced - skipped;
  if (failed > 0) return t("upgrade.donePartial", { replaced, total }, total);
  if (skipped > 0)
    return t("upgrade.doneSkipped", { replaced, skipped }, replaced);
  return t("upgrade.done", { replaced }, replaced);
});

function translateError(key: string | null): string {
  if (!key) return t("upgrade.error");
  const path = `upgrade.errors.${key as UpgradeErrorKey}`;
  const translated = t(path);
  return translated === path ? t("upgrade.error") : translated;
}

const errorMessage = computed(() => translateError(upgrade.errorDetail.value));

const errorTooltip = computed(() => {
  const msg = errorMessage.value;
  return msg !== t("upgrade.error") ? `${t("upgrade.error")}\n${msg}` : msg;
});

function handleDisconnect() {
  showDisconnectConfirm.value = true;
}

function confirmDisconnect() {
  showDisconnectConfirm.value = false;
  void upgrade.disconnect();
}

const { confirmUpgrade } = upgrade;
</script>

<template>
  <template v-if="upgrade.googlePhotosState.value !== 'unavailable'">
    <AsyncActionButton
      v-if="buttonState"
      :state="buttonState"
      :idle-icon="symOutlinedUpgrade"
      :idle-label="t('upgrade.button')"
      :progress-fraction="progressFraction"
      :progress-message="progressMessage"
      :done-message="doneMessage"
      @start="upgrade.start(props.albumId)"
      @cancel="upgrade.cancel()"
    />

    <button
      v-else-if="upgrade.phase.value === 'error'"
      class="action-btn error"
      :aria-label="t('upgrade.error')"
      @click="upgrade.start(props.albumId)"
    >
      <q-icon :name="symOutlinedError" size="var(--type-lg)" />
      {{ errorMessage }}
      <q-tooltip
        transition-show="scale"
        transition-hide="scale"
        class="q-menu"
      >
        {{ errorTooltip }}
      </q-tooltip>
    </button>

    <button
      v-else-if="!Platform.is.chrome"
      class="action-btn"
      aria-disabled="true"
      :aria-label="t('upgrade.button')"
    >
      <q-icon :name="symOutlinedUpgrade" size="var(--type-lg)" />
      {{ t("upgrade.button") }}
      <q-tooltip
        transition-show="scale"
        transition-hide="scale"
        class="q-menu"
      >
        <div class="chrome-tooltip">
          <p class="chrome-tooltip-title">
            {{ t("upgrade.errors.chromeOnly") }}
          </p>
          <p class="chrome-tooltip-sub text-faint">
            {{ t("upgrade.chromeOnlySub") }}
          </p>
        </div>
      </q-tooltip>
    </button>

    <div v-else class="split-btn">
      <button
        class="action-btn"
        :aria-label="t('upgrade.button')"
        @click="upgrade.start(props.albumId)"
      >
        <q-icon :name="symOutlinedUpgrade" size="var(--type-lg)" />
        {{ t("upgrade.button") }}
      </button>
      <button
        class="split-trigger"
        :aria-label="t('upgrade.options')"
        aria-haspopup="menu"
      >
        <q-icon :name="symOutlinedKeyboardArrowDown" size="var(--type-sm)" />
        <q-menu anchor="bottom end" self="top end" :offset="[0, 4]">
          <div class="split-menu">
            <button class="split-menu-item" @click="handleDisconnect">
              <q-icon :name="symOutlinedLinkOff" size="var(--type-sm)" />
              {{ t("upgrade.disconnect") }}
            </button>
          </div>
        </q-menu>
      </button>
    </div>

    <PromptDialog
      :model-value="upgrade.phase.value === 'onboarding'"
      :icon="symOutlinedUpgrade"
      variant="primary"
      :title="t('upgrade.onboarding.title')"
      :body="t('upgrade.onboarding.body')"
      :tip="t('upgrade.onboarding.tip')"
      :confirm-label="t('upgrade.onboarding.continue')"
      :cancel-label="t('common.cancel')"
      @update:model-value="onOnboardingVisibility"
      @confirm="confirmUpgrade"
    />

    <UpgradeMatchDialog
      :model-value="upgrade.phase.value === 'confirming'"
      :matched="upgrade.matchSummary.value?.matched ?? 0"
      :total="upgrade.matchSummary.value?.totalPicked ?? 0"
      :unmatched="upgrade.matchSummary.value?.unmatched ?? 0"
      :already-upgraded="upgrade.matchSummary.value?.alreadyUpgraded ?? 0"
      :new-this-round="upgrade.matchSummary.value?.newThisRound ?? 0"
      @update:model-value="onSummaryVisibility"
      @confirm="confirmUpgrade"
      @select-more="upgrade.selectMore()"
    />

    <PromptDialog
      v-model="showDisconnectConfirm"
      :icon="symOutlinedLinkOff"
      variant="warning"
      :title="t('upgrade.disconnectConfirm.title')"
      :body="t('upgrade.disconnectConfirm.body')"
      :confirm-label="t('upgrade.disconnectConfirm.confirm')"
      :cancel-label="t('common.cancel')"
      @confirm="confirmDisconnect"
    />
  </template>
</template>

<style lang="scss" scoped>
@use "@/styles/action-button" as *;
@include action-button;

.action-btn.error {
  border-color: var(--q-negative);
  color: var(--q-negative);

  &:hover {
    background: var(--q-negative);
    color: var(--bg);
  }
}

.action-btn[aria-disabled="true"] {
  opacity: 0.6;
  cursor: help;
}

.split-btn {
  display: inline-flex;
  align-items: stretch;

  .action-btn {
    border-start-end-radius: 0;
    border-end-end-radius: 0;
  }
}

.split-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 var(--gap-sm);
  min-width: 2.75rem;
  border: 1px solid var(--q-primary);
  border-inline-start: none;
  border-start-start-radius: 0;
  border-end-start-radius: 0;
  border-start-end-radius: var(--radius-sm);
  border-end-end-radius: var(--radius-sm);
  background: transparent;
  color: var(--q-primary);
  cursor: pointer;
  transition:
    background var(--duration-fast),
    color var(--duration-fast);

  &:hover {
    background: var(--q-primary);
    color: var(--bg);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.split-menu {
  padding: var(--gap-xs);
  min-width: 10rem;
}

.split-menu-item {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  width: 100%;
  padding: var(--gap-sm) var(--gap-md);
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  color: var(--text-muted);
  box-sizing: border-box;
  transition: background var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--text) 8%, transparent);
    color: var(--text);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: -1px;
  }
}

.chrome-tooltip {
  max-width: 22rem;
  padding: var(--gap-sm);
  font-size: var(--type-sm);
  line-height: 1.4;
}

.chrome-tooltip-title {
  margin: 0 0 var(--gap-xs);
  font-weight: 500;
}

.chrome-tooltip-sub {
  margin: 0;
}
</style>
