<script lang="ts" setup>
import type { UploadResult } from "@/client";
import { useDirectZipUpload } from "@/composables/useDirectZipUpload";
import { getSettings } from "@/config";
import { symOutlinedLuggage } from "@quasar/extras/material-symbols-outlined";
import { useQuasar } from "quasar";
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import TripPicker from "./TripPicker.vue";

const props = withDefaults(
  defineProps<{ preselectedIds?: readonly string[] }>(),
  { preselectedIds: () => [] },
);
const emit = defineEmits<{
  uploaded: [data: UploadResult];
}>();

const settings = getSettings();
const $q = useQuasar();
const { t } = useI18n();
const dragging = ref(false);
const dragDepth = ref(0);
const fileInputRef = ref<HTMLInputElement>();
const {
  file,
  status,
  progress,
  processingPhase,
  errorCode,
  choices,
  selectedIds,
  selectionSubmitting,
  selectionError,
  addFile,
  cancel,
  reset,
  submitSelection,
} = useDirectZipUpload({
  maxFileSize: settings.MAX_UPLOAD_SIZE_BYTES,
  onUploaded: (result) => emit("uploaded", result),
});

watch(status, (current) => {
  if (current !== "selecting" || selectedIds.value.length > 0) return;
  const available = new Set(choices.value.map(({ id }) => id));
  selectedIds.value = props.preselectedIds.filter((id) => available.has(id));
});

function pickFiles() {
  fileInputRef.value?.click();
}

function pickNewFile() {
  reset();
  pickFiles();
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = input.files?.[0];
  input.value = "";
  if (selected) handleFile(selected);
}

function onDragEnter() {
  dragDepth.value += 1;
  dragging.value = true;
}

function onDragLeave() {
  dragDepth.value -= 1;
  if (dragDepth.value === 0) dragging.value = false;
}

function onDrop(event: DragEvent) {
  dragDepth.value = 0;
  dragging.value = false;
  const dropped = event.dataTransfer?.files[0];
  if (dropped) handleFile(dropped);
}

function handleFile(selected: File) {
  if (status.value !== "idle") return;
  if (!selected.name.toLowerCase().endsWith(".zip") || selected.size === 0) {
    $q.notify({ type: "negative", message: t("register.badZip") });
    return;
  }
  if (selected.size > settings.MAX_UPLOAD_SIZE_BYTES) {
    $q.notify({
      type: "negative",
      message: t("register.fileTooLarge", {
        max: settings.MAX_UPLOAD_SIZE_BYTES / 1024 ** 3,
      }),
    });
    return;
  }
  addFile(selected);
}
</script>

<template>
  <div>
    <h3 class="upload-title text-h6 text-weight-semibold text-bright">
      <i18n-t keypath="register.uploadTitle">
        <template #file>
          <strong class="file-name">user_data.zip</strong>
        </template>
      </i18n-t>
    </h3>
    <input
      ref="fileInputRef"
      type="file"
      accept=".zip"
      class="hidden-input"
      @change="onFileSelected"
    />
    <TripPicker
      v-if="status === 'selecting'"
      v-model="selectedIds"
      :choices="choices"
      :submitting="selectionSubmitting"
      :error="selectionError"
      @submit="submitSelection"
    />
    <div v-else class="uploader full-width" :class="{ 'uploader--dnd': dragging }">
      <div
        v-if="file"
        class="uploader-header row no-wrap items-center q-gutter-x-sm"
      >
        <span class="text-body2 text-bright ellipsis">{{ file.name }}</span>
        <span
          v-if="status === 'uploading' || status === 'processing'"
          class="text-caption text-faint"
        >
          {{ Math.round(progress * 100) }}%
        </span>
        <q-space />
        <q-btn
          v-if="status === 'uploading'"
          flat
          dense
          size="sm"
          :label="t('common.cancel')"
          class="text-faint"
          @click="cancel"
        />
      </div>

      <div
        v-if="status === 'idle'"
        class="drop-zone column items-center justify-center"
        role="button"
        tabindex="0"
        :aria-label="t('register.dropZone')"
        @click="pickFiles"
        @keydown.enter.prevent="pickFiles"
        @keydown.space.prevent="pickFiles"
        @dragenter.prevent="onDragEnter"
        @dragover.prevent
        @dragleave.prevent="onDragLeave"
        @drop.prevent="onDrop"
      >
        <q-icon :name="symOutlinedLuggage" size="3rem" class="drop-zone-icon" />
        <span class="text-body2">{{ t("register.dropZone") }}</span>
      </div>

      <div
        v-else-if="status === 'uploading' || status === 'processing'"
        class="upload-progress"
        aria-live="polite"
      >
        <q-linear-progress
          :value="progress"
          color="primary"
          class="upload-bar"
          :aria-label="t('register.uploadProgress')"
        />
        <p class="text-caption text-faint">
          {{
            status === "processing"
              ? t(`register.uploadPhases.${processingPhase}`)
              : t("register.uploadPhases.uploading")
          }}
        </p>
      </div>

      <div v-else class="upload-error" aria-live="polite">
        <p>{{ t(`register.uploadErrors.${errorCode ?? "upload_failed"}`) }}</p>
        <q-btn
          color="primary"
          :label="t('register.uploadAgain')"
          @click="pickNewFile"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.hidden-input {
  display: none;
}

.upload-title {
  margin: 0 0 var(--gap-md-lg);
}

.file-name {
  font-weight: 700;
}

.uploader-header {
  padding: 0;
}

.drop-zone {
  padding: 3rem var(--gap-lg);
  gap: var(--gap-md-lg);
  cursor: pointer;
  border: 0.125rem dashed var(--border-color);
  border-radius: var(--radius-md);
  transition:
    border-color var(--duration-fast) ease,
    background var(--duration-fast) ease;
}

.drop-zone:hover,
.uploader--dnd .drop-zone {
  border-color: var(--q-primary);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}

.drop-zone:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
}

.drop-zone-icon {
  color: var(--text-faint);
}

.upload-progress {
  padding-top: var(--gap-md);
}

.upload-bar {
  border-radius: var(--radius-xs);
}
</style>
