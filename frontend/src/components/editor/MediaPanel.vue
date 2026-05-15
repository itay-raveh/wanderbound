<script lang="ts" setup>
import type { AlbumMedia } from "@/client";
import type { ExternalImportTarget } from "@/composables/useAddExternalMedia";
import ExternalMediaReviewDialog from "./ExternalMediaReviewDialog.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import UpgradeMediaButton from "./UpgradeMediaButton.vue";
import { useAddExternalMedia } from "@/composables/useAddExternalMedia";
import { useExternalMediaSources } from "@/composables/useExternalMediaSources";
import { useMediaUndo } from "@/composables/useMediaUndo";
import { useReplaceExternalMedia } from "@/composables/useReplaceExternalMedia";
import { qualitySummary } from "@/composables/usePhotoQuality";
import { THUMB_WIDTHS, mediaThumbUrl } from "@/utils/media";
import type { MediaResolutionWarningPreset } from "@/utils/photoQuality";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  matAddPhotoAlternate,
  matArrowForward,
  matCheckCircle,
  matComputer,
  matImage,
  matKeyboardArrowDown,
  matPublishedWithChanges,
  matUndo,
  matWarning,
} from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  albumId: string;
  context: "step" | "cover" | "map" | "overview" | "empty";
  stepId?: number;
  targetLabel?: string | null;
  media?: AlbumMedia[];
  resolutionWarningPreset: MediaResolutionWarningPreset;
}>();

const emit = defineEmits<{
  "update:resolutionWarningPreset": [value: MediaResolutionWarningPreset];
}>();

const resolutionWarningOptions = computed<
  { label: string; value: MediaResolutionWarningPreset }[]
>(() => [
  { label: t("editor.resolutionWarningsOff"), value: "off" },
  { label: t("editor.resolutionWarningsRelaxed"), value: "relaxed" },
  { label: t("editor.resolutionWarningsPrint"), value: "print" },
]);

const addMedia = useAddExternalMedia(() => props.albumId);
const replaceMedia = useReplaceExternalMedia();
const undo = useMediaUndo(() => props.albumId);
const sources = useExternalMediaSources();

const importInputRef = ref<HTMLInputElement | null>(null);
const replaceInputRef = ref<HTMLInputElement | null>(null);
const importMenuOpen = ref(false);
const replaceMenuOpen = ref(false);

const importTarget = computed<ExternalImportTarget | null>(() => {
  if (props.context === "step" && props.stepId != null) {
    return { context: "step", stepId: props.stepId };
  }
  if (props.context === "cover") return { context: "cover" };
  return null;
});

const importLabel = computed(() => {
  if (props.context === "step" && props.stepId != null) {
    return t("externalMedia.import.toTarget", {
      target: props.targetLabel ?? t("externalMedia.import.unnamedStep"),
    });
  }
  if (props.context === "cover") return t("externalMedia.import.toCover");
  return t("externalMedia.import.shortAction");
});

const importHelper = computed(() => {
  if (props.context === "map") return t("externalMedia.targets.mapUnavailable");
  if (props.context === "overview")
    return t("externalMedia.targets.overviewUnavailable");
  return t("externalMedia.targets.none");
});

type QualityTier = "warning" | "caution";

const qualityTier = computed<QualityTier | null>(() => {
  const { warning, caution } = qualitySummary.value;
  if (warning > 0) return "warning";
  if (caution > 0) return "caution";
  return null;
});

const qualityChipLabel = computed(() => {
  const { warning, caution } = qualitySummary.value;
  if (warning > 0)
    return t("externalMedia.quality.warningChip", { count: warning });
  if (caution > 0)
    return t("externalMedia.quality.cautionChip", { count: caution });
  return "";
});

// Cycles through quality-badge elements rendered by MediaItem so each click
// reveals the next problem photo instead of always the first one.
const warningCursor = ref(0);
const warningAnnouncement = ref("");

function jumpToNextWarning() {
  const badges = Array.from(
    document.querySelectorAll<HTMLElement>(
      ".quality-badge.warning, .quality-badge.caution",
    ),
  );
  if (badges.length === 0) return;
  const index = warningCursor.value % badges.length;
  const target = badges[index];
  warningCursor.value = (index + 1) % badges.length;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.focus({ preventScroll: true });
  warningAnnouncement.value = t("externalMedia.quality.jumpAnnounce", {
    index: index + 1,
    total: badges.length,
  });
}

const selectedMediaName = computed(() => replaceMedia.selectedMediaName.value);
const hasSelectedMedia = computed(() => selectedMediaName.value != null);

const selectedMedia = computed<AlbumMedia | null>(() => {
  const name = selectedMediaName.value;
  if (!name || !props.media) return null;
  return props.media.find((m) => m.name === name) ?? null;
});

const selectedThumbUrl = computed(() => {
  const m = selectedMedia.value;
  if (!m) return null;
  return mediaThumbUrl(m.name, props.albumId, THUMB_WIDTHS[0], m.updated_at);
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
  await addMedia.importDevice(files, target);
}

async function runGoogleImport() {
  const target = importTarget.value;
  if (!target || addMedia.googlePhotosState.value === "unavailable") return;
  await addMedia.importGoogle(target);
}

function pickDeviceImport() {
  if (!importTarget.value) return;
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
  replaceInputRef.value?.click();
}

async function onReplacementFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  await replaceMedia.prepareDeviceReview(file);
}

const REPLACE_FLASH_MS = 5000;
const justReplaced = ref(false);
let flashTimer: ReturnType<typeof setTimeout> | null = null;

function flashUndo() {
  justReplaced.value = true;
  if (flashTimer != null) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    justReplaced.value = false;
    flashTimer = null;
  }, REPLACE_FLASH_MS);
}

async function confirmDeviceReplacement() {
  const mediaName = await replaceMedia.confirmDeviceReplacement();
  if (!mediaName) return;
  undo.rememberReplacement(mediaName);
  flashUndo();
}

async function replaceFromGoogle() {
  const mediaName = await replaceMedia.replaceFromGoogle();
  if (!mediaName) return;
  undo.rememberReplacement(mediaName);
  flashUndo();
}

async function undoLastReplacement() {
  justReplaced.value = false;
  if (flashTimer != null) {
    clearTimeout(flashTimer);
    flashTimer = null;
  }
  await undo.undo();
}

const replaceError = computed(() =>
  replaceMedia.phase.value === "error" ? replaceMedia.errorDetail.value : null,
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

    <section class="quality-section" aria-labelledby="media-panel-quality-title">
      <div class="quality-header">
        <h3 id="media-panel-quality-title" class="quality-section-title">
          {{ t("editor.photoQuality") }}
        </h3>
        <button
          v-if="qualityTier"
          type="button"
          class="quality-chip"
          :class="qualityTier"
          :title="t('externalMedia.quality.jumpToNext')"
          @click="jumpToNextWarning"
        >
          <q-icon :name="matWarning" size="var(--type-sm)" class="chip-icon" />
          <span>{{ qualityChipLabel }}</span>
          <q-icon
            :name="matArrowForward"
            size="var(--type-sm)"
            class="chip-icon rtl-flip"
          />
        </button>
        <span
          v-else-if="resolutionWarningPreset !== 'off'"
          class="quality-chip all-clear"
        >
          <q-icon :name="matCheckCircle" size="var(--type-sm)" class="chip-icon" />
          <span>{{ t("externalMedia.quality.allClear") }}</span>
        </span>
      </div>
      <SegmentedControl
        :model-value="resolutionWarningPreset"
        :options="resolutionWarningOptions"
        :aria-label="t('editor.photoQuality')"
        @update:model-value="
          (v: MediaResolutionWarningPreset) =>
            emit('update:resolutionWarningPreset', v)
        "
      />
      <UpgradeMediaButton :album-id="albumId" />
    </section>
    <span class="sr-only" role="status" aria-live="polite">{{
      warningAnnouncement
    }}</span>

    <button
      v-if="importTarget"
      type="button"
      class="media-cta primary"
      :disabled="addMedia.isBusy.value"
      :aria-label="t('externalMedia.import.action')"
      aria-haspopup="menu"
      :aria-expanded="importMenuOpen"
    >
      <q-icon :name="matAddPhotoAlternate" size="var(--type-md)" />
      <span class="cta-label">{{ importLabel }}</span>
      <q-icon
        :name="matKeyboardArrowDown"
        size="var(--type-sm)"
        class="cta-caret"
      />
      <q-menu
        v-model="importMenuOpen"
        anchor="bottom start"
        self="top start"
        :offset="[0, 4]"
        fit
      >
        <div class="cta-menu" role="menu">
          <button
            type="button"
            class="cta-menu-item"
            role="menuitem"
            v-close-popup
            @click="pickDeviceImport"
          >
            <q-icon :name="matComputer" size="var(--type-md)" />
            <span>{{ t("mediaImport.device") }}</span>
          </button>
          <button
            type="button"
            class="cta-menu-item"
            role="menuitem"
            :disabled="!sources.googleAvailable.value"
            v-close-popup
            @click="runGoogleImport"
          >
            <q-icon name="img:/google-photos.svg" size="var(--type-md)" />
            <span>{{ t("mediaImport.googlePhotos") }}</span>
          </button>
        </div>
      </q-menu>
    </button>
    <p v-else class="media-helper">{{ importHelper }}</p>

    <div
      v-if="hasSelectedMedia || undo.currentUndo.value"
      class="selected-section"
    >
      <div v-if="hasSelectedMedia" class="replace-swap">
        <div class="swap-cell current" aria-hidden="true">
          <img
            v-if="selectedThumbUrl"
            :src="selectedThumbUrl"
            alt=""
            decoding="async"
          />
          <q-icon v-else :name="matImage" size="var(--type-lg)" />
        </div>
        <q-icon
          :name="matArrowForward"
          size="var(--type-md)"
          class="swap-arrow rtl-flip"
        />
        <button
          type="button"
          class="swap-cell target"
          :disabled="replaceMedia.isBusy.value"
          :aria-label="t('externalMedia.replace.action')"
          aria-haspopup="menu"
          :aria-expanded="replaceMenuOpen"
        >
          <q-icon :name="matPublishedWithChanges" size="var(--type-lg)" />
          <q-menu
            v-model="replaceMenuOpen"
            anchor="bottom middle"
            self="top middle"
            :offset="[0, 4]"
          >
            <div class="cta-menu" role="menu">
              <button
                type="button"
                class="cta-menu-item"
                role="menuitem"
                v-close-popup
                @click="pickDeviceReplacement"
              >
                <q-icon :name="matComputer" size="var(--type-md)" />
                <span>{{ t("mediaImport.device") }}</span>
              </button>
              <button
                type="button"
                class="cta-menu-item"
                role="menuitem"
                :disabled="replaceMedia.googlePhotosState.value === 'unavailable'"
                v-close-popup
                @click="replaceFromGoogle"
              >
                <q-icon name="img:/google-photos.svg" size="var(--type-md)" />
                <span>{{ t("mediaImport.googlePhotos") }}</span>
              </button>
            </div>
          </q-menu>
        </button>
      </div>
      <button
        v-if="undo.currentUndo.value"
        type="button"
        class="media-cta subtle"
        :class="{ 'just-replaced': justReplaced }"
        :disabled="undo.currentUndo.value.pending"
        :aria-label="t('externalMedia.undo.action')"
        @click="undoLastReplacement"
      >
        <q-icon :name="matUndo" size="var(--type-md)" />
        <span class="cta-label">{{ t("externalMedia.undo.shortAction") }}</span>
      </button>
      <p v-if="replaceError" class="media-error">{{ replaceError }}</p>
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
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
  padding: var(--gap-md) var(--gap-lg);
}

.hidden-input {
  position: absolute;
  width: 0.0625rem;
  height: 0.0625rem;
  opacity: 0;
  pointer-events: none;
}

.sr-only {
  position: absolute;
  width: 0.0625rem;
  height: 0.0625rem;
  margin: -0.0625rem;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.quality-section {
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
}

.quality-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  column-gap: var(--gap-sm);
  row-gap: var(--gap-xs);
}

.quality-section-title {
  margin: 0;
  font-size: var(--type-xs);
  font-weight: 500;
  color: var(--text-muted);
}

.quality-chip {
  all: unset;
  display: inline-flex;
  align-items: center;
  gap: var(--gap-xs);
  min-height: 2rem;
  padding: 0.25rem var(--gap-sm);
  border-radius: var(--radius-xs);
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  transition:
    background var(--duration-fast),
    color var(--duration-fast);

  &.warning .chip-icon {
    color: var(--q-negative);
  }

  &.caution .chip-icon {
    color: var(--q-warning);
  }

  &.all-clear {
    color: var(--text-muted);
    font-weight: 400;
    cursor: default;
  }

  &.all-clear .chip-icon {
    color: inherit;
  }

  &:not(.all-clear):hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.media-cta {
  all: unset;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  width: 100%;
  min-height: 2.75rem;
  padding: 0 var(--gap-md-lg);
  border: 1px solid var(--q-primary);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--q-primary);
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 500;
  cursor: pointer;
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast),
    color var(--duration-fast);

  &:hover:not(:disabled) {
    background: var(--q-primary);
    color: var(--bg);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }

  &:disabled {
    cursor: default;
    opacity: 0.5;
  }
}

.media-cta.primary {
  background: var(--q-primary);
  color: var(--bg);

  &:hover:not(:disabled) {
    background: color-mix(in srgb, var(--q-primary) 88%, var(--text));
    border-color: color-mix(in srgb, var(--q-primary) 88%, var(--text));
    color: var(--bg);
  }
}

.media-cta.subtle {
  border-color: transparent;
  color: var(--text-muted);

  &:hover:not(:disabled) {
    background: transparent;
    color: var(--text);
    border-color: var(--text-faint);
  }
}

.media-cta.subtle.just-replaced {
  border-color: var(--q-primary);
  color: var(--q-primary);
}

.media-cta:not(.primary) .cta-caret {
  opacity: 0.7;
}

.media-helper {
  margin: 0;
  font-size: var(--type-xs);
  line-height: 1.5;
  color: var(--text-muted);
}

.media-error {
  margin: 0;
  font-size: var(--type-xs);
  line-height: 1.4;
  color: var(--q-negative);
}

.selected-section {
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
}

.replace-swap {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
}

.swap-cell {
  flex: 1;
  min-width: 3rem;
  max-width: 6rem;
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--text) 4%, transparent);
  color: var(--text-muted);
}

.swap-cell.current img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.swap-cell.target {
  all: unset;
  box-sizing: border-box;
  flex: 1;
  min-width: 3rem;
  max-width: 6rem;
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  border: 1px solid var(--text-faint);
  background: transparent;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    border-color var(--duration-fast),
    background var(--duration-fast),
    color var(--duration-fast);

  &:hover:not(:disabled) {
    border-color: var(--q-primary);
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 8%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }

  &:disabled {
    cursor: default;
    opacity: 0.5;
  }
}

.swap-arrow {
  color: var(--text-faint);
  flex-shrink: 0;
}

.cta-menu {
  display: grid;
  gap: var(--gap-xs);
  min-width: 13rem;
  padding: var(--gap-xs);
}

.cta-menu-item {
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

.dialog-header {
  gap: var(--gap-sm);
}

.import-dialog {
  width: min(24rem, 90vw);
  border-radius: var(--radius-sm);
}

@media (prefers-reduced-motion: reduce) {
  .quality-chip,
  .media-cta,
  .swap-cell.target {
    transition: none;
  }
}
</style>
