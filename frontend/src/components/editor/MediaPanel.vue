<script lang="ts" setup>
import type { ExternalImportTarget } from "@/composables/useAddExternalMedia";
import ExternalMediaReviewDialog from "./ExternalMediaReviewDialog.vue";
import UpgradeMediaButton from "./UpgradeMediaButton.vue";
import { useAddExternalMedia } from "@/composables/useAddExternalMedia";
import { useExternalMediaSources } from "@/composables/useExternalMediaSources";
import { useMediaUndo } from "@/composables/useMediaUndo";
import { useReplaceExternalMedia } from "@/composables/useReplaceExternalMedia";
import { qualitySummary } from "@/composables/usePhotoQuality";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  matAddPhotoAlternate,
  matComputer,
  matImage,
  matPublishedWithChanges,
  matUndo,
} from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  albumId: string;
  context: "step" | "cover" | "map" | "overview" | "empty";
  stepId?: number;
}>();

const addMedia = useAddExternalMedia(() => props.albumId);
const replaceMedia = useReplaceExternalMedia();
const undo = useMediaUndo(() => props.albumId);
const sources = useExternalMediaSources();

const importInputRef = ref<HTMLInputElement | null>(null);
const replaceInputRef = ref<HTMLInputElement | null>(null);
const showImportMenu = ref(false);
const showReplaceMenu = ref(false);

const importTarget = computed<ExternalImportTarget | null>(() => {
  if (props.context === "step" && props.stepId != null) {
    return { context: "step", stepId: props.stepId };
  }
  if (props.context === "cover") return { context: "cover" };
  return null;
});

const importTargetLabel = computed(() => {
  if (props.context === "step" && props.stepId != null) {
    return t("externalMedia.targets.stepUnused", { stepId: props.stepId });
  }
  if (props.context === "cover") {
    return t("externalMedia.targets.coverCandidates");
  }
  if (props.context === "map") return t("externalMedia.targets.mapUnavailable");
  if (props.context === "overview")
    return t("externalMedia.targets.overviewUnavailable");
  return t("externalMedia.targets.none");
});

const qualitySummaryLabel = computed(() => {
  const { warning, caution } = qualitySummary.value;
  if (warning === 0 && caution === 0) {
    return t("externalMedia.quality.allGood");
  }
  return t("externalMedia.quality.needsAttention", { warning, caution });
});

const importProgressFraction = computed(() => {
  const { done, total } = addMedia.progress.value;
  return total > 0 ? done / total : 0;
});

const importDialogTitle = computed(() => {
  switch (addMedia.phase.value) {
    case "authorizing":
      return t("mediaImport.authorizing");
    case "picking":
      return t("mediaImport.picking");
    case "uploading":
      return t("mediaImport.uploading");
    case "processing":
      return t("mediaImport.processing");
    case "done":
      return t(
        "mediaImport.done",
        { count: addMedia.importedCount.value },
        addMedia.importedCount.value,
      );
    case "error":
      return addMedia.errorDetail.value ?? t("mediaImport.error");
    default:
      return "";
  }
});

const showReview = computed({
  get: () => replaceMedia.review.value !== null,
  set: (value: boolean) => {
    if (!value) replaceMedia.cancelReview();
  },
});

async function runDeviceImport(files: FileList | File[]) {
  const target = importTarget.value;
  if (!target) return;
  showImportMenu.value = false;
  await addMedia.importDevice(files, target);
}

async function runGoogleImport() {
  const target = importTarget.value;
  if (!target || addMedia.googlePhotosState.value === "unavailable") return;
  showImportMenu.value = false;
  await addMedia.importGoogle(target);
}

function pickDeviceImport() {
  if (!importTarget.value) return;
  showImportMenu.value = false;
  importInputRef.value?.click();
}

async function onImportFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = "";
  if (files.length === 0) return;
  await runDeviceImport(files);
}

function pickDeviceReplacement() {
  showReplaceMenu.value = false;
  replaceInputRef.value?.click();
}

async function onReplacementFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  await replaceMedia.prepareDeviceReview(file);
}

async function confirmDeviceReplacement() {
  const mediaName = await replaceMedia.confirmDeviceReplacement();
  if (!mediaName) return;
  undo.rememberReplacement(mediaName);
}

async function replaceFromGoogle() {
  showReplaceMenu.value = false;
  const mediaName = await replaceMedia.replaceFromGoogle();
  if (!mediaName) return;
  undo.rememberReplacement(mediaName);
}

async function undoLastReplacement() {
  await undo.undo();
}

const replaceError = computed(() =>
  replaceMedia.phase.value === "error" ? replaceMedia.errorDetail.value : null,
);

const importError = computed(() =>
  addMedia.phase.value === "error" ? addMedia.errorDetail.value : null,
);
</script>

<template>
  <div class="media-panel">
    <input
      ref="importInputRef"
      type="file"
      class="hidden-input"
      accept="image/*,video/*"
      multiple
      @change="onImportFilesSelected"
    />
    <input
      ref="replaceInputRef"
      type="file"
      class="hidden-input"
      accept="image/*,video/*"
      @change="onReplacementFileSelected"
    />

    <div class="panel-block">
      <div class="panel-row">
        <div>
          <div class="panel-kicker">{{ t("externalMedia.google.title") }}</div>
          <div class="panel-value">{{ sources.googleStatusLabel }}</div>
        </div>
        <UpgradeMediaButton :album-id="albumId" />
      </div>
      <div class="panel-note">{{ qualitySummaryLabel }}</div>
    </div>

    <div class="panel-block">
      <div class="panel-row panel-row-stack">
        <div>
          <div class="panel-kicker">{{ t("externalMedia.import.label") }}</div>
          <div class="panel-value">{{ importTargetLabel }}</div>
        </div>
        <div class="panel-action-wrap">
          <button
            type="button"
            class="panel-action primary"
            :disabled="!importTarget || addMedia.isBusy.value"
            aria-haspopup="menu"
            @click="showImportMenu = true"
          >
            <q-icon :name="matAddPhotoAlternate" size="var(--type-md)" />
            <span>{{ t("externalMedia.import.action") }}</span>
          </button>
          <div v-if="showImportMenu" class="action-menu" role="menu">
            <button
              type="button"
              class="action-menu-item"
              role="menuitem"
              @click="pickDeviceImport"
            >
              <q-icon :name="matComputer" size="var(--type-md)" />
              <span>{{ t("mediaImport.device") }}</span>
            </button>
            <button
              type="button"
              class="action-menu-item"
              role="menuitem"
              :disabled="!sources.googleAvailable.value"
              @click="runGoogleImport"
            >
              <q-icon name="img:/google-photos.svg" size="var(--type-md)" />
              <span>{{ t("mediaImport.googlePhotos") }}</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="importError" class="panel-error">{{ importError }}</div>
    </div>

    <div class="panel-block">
      <div class="panel-row panel-row-stack">
        <div>
          <div class="panel-kicker">{{ t("externalMedia.replace.label") }}</div>
          <div class="panel-value">
            {{
              replaceMedia.selectedMediaName.value ??
              t("externalMedia.replace.noneSelected")
            }}
          </div>
        </div>
        <div class="panel-action-wrap">
          <button
            type="button"
            class="panel-action"
            :disabled="!replaceMedia.selectedMediaName.value || replaceMedia.isBusy.value"
            aria-haspopup="menu"
            @click="showReplaceMenu = true"
          >
            <q-icon :name="matPublishedWithChanges" size="var(--type-md)" />
            <span>{{ t("externalMedia.replace.action") }}</span>
          </button>
          <div v-if="showReplaceMenu" class="action-menu" role="menu">
            <button
              type="button"
              class="action-menu-item"
              role="menuitem"
              @click="pickDeviceReplacement"
            >
              <q-icon :name="matComputer" size="var(--type-md)" />
              <span>{{ t("mediaImport.device") }}</span>
            </button>
            <button
              type="button"
              class="action-menu-item"
              role="menuitem"
              :disabled="replaceMedia.googlePhotosState.value === 'unavailable'"
              @click="replaceFromGoogle"
            >
              <q-icon name="img:/google-photos.svg" size="var(--type-md)" />
              <span>{{ t("mediaImport.googlePhotos") }}</span>
            </button>
          </div>
        </div>
      </div>
      <div v-if="replaceError" class="panel-error">{{ replaceError }}</div>
    </div>

    <div v-if="undo.currentUndo.value" class="panel-block undo-block">
      <div>
        <div class="panel-kicker">{{ t("externalMedia.undo.label") }}</div>
        <div class="panel-value">{{ undo.currentUndo.value.mediaName }}</div>
      </div>
      <button
        type="button"
        class="panel-action subtle"
        :disabled="undo.currentUndo.value.pending"
        @click="undoLastReplacement"
      >
        <q-icon :name="matUndo" size="var(--type-md)" />
        <span>{{ t("externalMedia.undo.action") }}</span>
      </button>
    </div>

    <q-dialog
      :model-value="addMedia.phase.value !== 'idle'"
      persistent
      @hide="addMedia.cancel"
    >
      <q-card class="import-dialog">
        <q-card-section class="row no-wrap items-center dialog-header">
          <q-icon :name="matImage" size="1.5rem" />
          <div class="text-subtitle1 text-weight-semibold">
            {{ importDialogTitle }}
          </div>
        </q-card-section>
        <q-card-section v-if="addMedia.isBusy.value">
          <q-linear-progress
            :value="importProgressFraction"
            :indeterminate="importProgressFraction === 0"
            color="primary"
            rounded
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-if="addMedia.isBusy.value"
            flat
            no-caps
            :label="t('common.cancel')"
            @click="addMedia.cancel"
          />
          <q-btn
            v-else-if="addMedia.phase.value === 'error'"
            flat
            no-caps
            color="primary"
            :label="t('common.close')"
            @click="addMedia.cancel"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <ExternalMediaReviewDialog
      v-model="showReview"
      :review="replaceMedia.review.value"
      :replacing="replaceMedia.phase.value === 'replacing'"
      @confirm="confirmDeviceReplacement"
    />
  </div>
</template>

<style lang="scss" scoped>
.media-panel {
  position: relative;
  display: grid;
  gap: var(--gap-md);
  padding: var(--gap-md);
}

.hidden-input {
  position: absolute;
  width: 0.0625rem;
  height: 0.0625rem;
  opacity: 0;
  pointer-events: none;
}

.panel-block {
  display: grid;
  gap: var(--gap-sm);
  padding: var(--gap-md);
  border: 1px solid color-mix(in srgb, var(--border-color) 75%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg) 78%, transparent);
}

.panel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-md);
}

.panel-row-stack {
  align-items: flex-start;
}

.panel-kicker {
  font-size: var(--type-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--text-muted);
}

.panel-value {
  color: var(--text-bright);
  line-height: 1.5;
}

.panel-note {
  color: var(--text-muted);
  font-size: var(--type-sm);
  line-height: 1.5;
}

.panel-action-wrap {
  position: relative;
}

.panel-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  min-height: 2.5rem;
  padding: 0 var(--gap-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-bright);
  font-size: var(--type-sm);
  font-weight: 600;
  cursor: pointer;

  &:disabled {
    cursor: default;
    opacity: 0.5;
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.panel-action.primary {
  border-color: var(--q-primary);
  background: var(--q-primary);
  color: var(--bg);
}

.panel-action.subtle {
  justify-self: start;
}

.action-menu {
  position: absolute;
  z-index: 10;
  top: calc(100% + var(--gap-xs));
  right: 0;
  display: grid;
  gap: var(--gap-xs);
  min-width: 13rem;
  padding: var(--gap-xs);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg);
  box-shadow: var(--shadow-md);
}

.action-menu-item {
  all: unset;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
  width: 100%;
  min-height: 2.25rem;
  padding: 0 var(--gap-sm);
  border-radius: var(--radius-xs);
  color: var(--text);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: var(--type-sm);

  &:hover:not(:disabled),
  &:focus-visible {
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  &:disabled {
    cursor: default;
    opacity: 0.45;
  }
}

.panel-error {
  color: var(--q-negative);
  font-size: var(--type-sm);
  line-height: 1.5;
}

.undo-block {
  align-items: center;
  grid-template-columns: minmax(0, 1fr) auto;
}

.dialog-header {
  gap: var(--gap-sm);
}

.import-dialog {
  width: min(24rem, 90vw);
  border-radius: var(--radius-sm);
}

@media (max-width: 760px) {
  .panel-row,
  .undo-block {
    grid-template-columns: 1fr;
    display: grid;
    justify-items: start;
  }
}
</style>
