<script lang="ts" setup>
import type { AlbumMedia } from "@/client";
import type { ExternalImportTarget } from "@/composables/useAddExternalMedia";
import ExternalMediaReviewDialog from "./ExternalMediaReviewDialog.vue";
import SegmentedControl from "@/components/ui/SegmentedControl.vue";
import UpgradeMediaButton from "./UpgradeMediaButton.vue";
import { useAddExternalMedia } from "@/composables/useAddExternalMedia";
import { useExternalMediaSources } from "@/composables/useExternalMediaSources";
import { useMediaUndo } from "@/composables/useMediaUndo";
import {
  useReplaceExternalMedia,
  type ReplacementResult,
} from "@/composables/useReplaceExternalMedia";
import {
  jumpToNextQualityBadge,
  qualitySummary,
} from "@/composables/usePhotoQuality";
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

const liveAnnouncement = ref("");

function jumpToNextWarning() {
  const result = jumpToNextQualityBadge();
  if (!result) return;
  liveAnnouncement.value = t("externalMedia.quality.jumpAnnounce", {
    index: result.index + 1,
    total: result.total,
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

function settleReplacement(result: ReplacementResult | null, started: boolean) {
  if (!started) return;
  if (result) {
    undo.rememberReplacement(result);
    return;
  }
  if (replaceError.value) undo.failReplacement(replaceError.value);
  else undo.cancelReplacement();
}

async function confirmDeviceReplacement() {
  undo.startReplacement();
  const result = await replaceMedia.confirmDeviceReplacement();
  settleReplacement(result, true);
}

async function replaceFromGoogle() {
  let started = false;
  const result = await replaceMedia.replaceFromGoogle(() => {
    started = true;
    undo.startReplacement();
  });
  settleReplacement(result, started);
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

    <section
      class="quality-section"
      aria-labelledby="media-panel-quality-title"
    >
      <div class="quality-header">
        <div id="media-panel-quality-title" class="quality-section-title">
          {{ t("editor.photoQuality") }}
        </div>
        <button
          v-if="qualityTier"
          type="button"
          class="quality-chip"
          :class="qualityTier"
          @click="jumpToNextWarning"
        >
          <q-icon :name="matWarning" size="var(--type-sm)" class="chip-icon" />
          <span>{{ qualityChipLabel }}</span>
          <q-icon
            :name="matArrowForward"
            size="var(--type-sm)"
            class="chip-icon rtl-flip"
          />
          <q-tooltip>{{ t("externalMedia.quality.jumpToNext") }}</q-tooltip>
        </button>
        <span
          v-else-if="resolutionWarningPreset !== 'off'"
          class="quality-chip all-clear"
        >
          <q-icon
            :name="matCheckCircle"
            size="var(--type-sm)"
            class="chip-icon"
          />
          <span>{{ t("externalMedia.quality.allClear") }}</span>
        </span>
      </div>
      <div class="quality-controls">
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
        <div v-if="importTarget" class="import-cta">
          <button
            type="button"
            class="media-cta primary import-cta-main"
            :class="{ 'has-trailing': sources.googleAvailable.value }"
            :disabled="addMedia.isBusy.value"
            :aria-label="t('externalMedia.import.action')"
            @click="pickDeviceImport"
          >
            <q-icon :name="matAddPhotoAlternate" size="var(--type-md)" />
            <span class="cta-label">{{ importLabel }}</span>
          </button>
          <button
            v-if="sources.googleAvailable.value"
            type="button"
            class="import-cta-trigger"
            :disabled="addMedia.isBusy.value"
            :aria-label="t('externalMedia.import.moreOptions')"
            aria-haspopup="menu"
            :aria-expanded="importMenuOpen"
          >
            <q-icon :name="matKeyboardArrowDown" size="var(--type-sm)" />
            <q-menu
              v-model="importMenuOpen"
              anchor="bottom end"
              self="top end"
              :offset="[0, 4]"
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
                  v-close-popup
                  @click="runGoogleImport"
                >
                  <q-icon name="img:/google-photos.svg" size="var(--type-md)" />
                  <span>{{ t("mediaImport.googlePhotos") }}</span>
                </button>
              </div>
            </q-menu>
          </button>
        </div>
        <p v-else class="media-helper">{{ importHelper }}</p>
      </div>
    </section>
    <span class="sr-only" role="status" aria-live="polite">{{
      liveAnnouncement
    }}</span>

    <div v-if="hasSelectedMedia" class="selected-section">
      <div class="replace-swap">
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
          <q-tooltip>{{ t("externalMedia.replace.action") }}</q-tooltip>
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
                :disabled="
                  replaceMedia.googlePhotosState.value === 'unavailable'
                "
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
    </div>

    <q-dialog
      :model-value="addMedia.phase.value !== 'idle'"
      persistent
      @hide="addMedia.cancel"
    >
      <q-card class="import-dialog">
        <header class="import-dialog-header">
          <q-icon :name="matImage" size="var(--type-lg)" />
          <h3 class="import-dialog-title">{{ importDialogTitle }}</h3>
        </header>
        <q-linear-progress
          v-if="addMedia.isBusy.value"
          :value="importProgressFraction"
          :indeterminate="importProgressFraction === 0"
          color="primary"
          rounded
          class="import-dialog-progress"
        />
        <div class="import-dialog-actions">
          <button
            v-if="addMedia.isBusy.value"
            type="button"
            class="media-cta subtle"
            @click="addMedia.cancel"
          >
            <span class="cta-label">{{ t("common.cancel") }}</span>
          </button>
          <button
            v-else-if="addMedia.phase.value === 'error'"
            type="button"
            class="media-cta"
            @click="addMedia.cancel"
          >
            <span class="cta-label">{{ t("common.close") }}</span>
          </button>
        </div>
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

<style lang="scss" scoped src="./MediaPanel.scss"></style>
