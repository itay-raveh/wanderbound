<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UploadResult } from "@/client";
import type { Provider } from "@/router";
import { useQuasar } from "quasar";
import { onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { symOutlinedLuggage } from "@quasar/extras/material-symbols-outlined";

const props = defineProps<{
  credential?: string;
  provider?: Provider;
}>();

const emit = defineEmits<{
  uploaded: [data: UploadResult];
}>();

const baseUrl = client.getConfig().baseUrl;
const CHUNK_SIZE = 80 * 1024 * 1024; // 80 MiB
const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 2000, 4000];

const maxUploadGb = Number(import.meta.env.VITE_MAX_UPLOAD_GB) || 4;
const maxFileSize = maxUploadGb * 1024 * 1024 * 1024;

const $q = useQuasar();
const { t } = useI18n();

const file = ref<File | null>(null);
const uploading = ref(false);
const progress = ref(0);
const dragging = ref(false);
const dragDepth = ref(0);
const fileInputRef = ref<HTMLInputElement>();
const abortController = ref<AbortController | null>(null);

onUnmounted(() => abortController.value?.abort());

function buildAuthForm(): FormData {
  const form = new FormData();
  if (props.credential) form.append("credential", props.credential);
  if (props.provider) form.append("provider", props.provider);
  return form;
}

function pickFiles() {
  fileInputRef.value?.click();
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = input.files?.[0];
  input.value = "";
  if (selected) handleFile(selected);
}

function onDragEnter() {
  dragDepth.value++;
  dragging.value = true;
}

function onDragLeave() {
  if (--dragDepth.value === 0) dragging.value = false;
}

function onDrop(event: DragEvent) {
  dragDepth.value = 0;
  dragging.value = false;
  const dropped = event.dataTransfer?.files[0];
  if (dropped) handleFile(dropped);
}

function handleFile(selected: File) {
  if (uploading.value) return;
  if (!selected.name.endsWith(".zip")) {
    $q.notify({ type: "negative", message: t("register.uploadFailed") });
    return;
  }
  if (selected.size > maxFileSize) {
    $q.notify({
      type: "negative",
      message: t("register.fileTooLarge", { max: maxUploadGb }),
    });
    return;
  }
  file.value = selected;
  void startUpload(selected);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function uploadChunkWithRetry(
  url: string,
  blob: Blob,
  chunkStart: number,
  totalSize: number,
  signal: AbortSignal,
): Promise<void> {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", url);
        xhr.withCredentials = true;
        xhr.timeout = 120_000; // 2 minutes per chunk

        const onAbort = () => {
          xhr.abort();
          reject(new DOMException("Aborted", "AbortError"));
        };
        signal.addEventListener("abort", onAbort, { once: true });

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            progress.value = (chunkStart + e.loaded) / totalSize;
          }
        };
        xhr.onload = () => {
          signal.removeEventListener("abort", onAbort);
          if (xhr.status === 204) resolve();
          else reject(new Error(`${xhr.status}`));
        };
        xhr.onerror = () => {
          signal.removeEventListener("abort", onAbort);
          reject(new Error("Network error"));
        };
        xhr.ontimeout = () => {
          signal.removeEventListener("abort", onAbort);
          reject(new Error("Timeout"));
        };
        xhr.send(blob);
      });
      return;
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      if (attempt === MAX_RETRIES) throw e;
      await sleep(RETRY_DELAYS[attempt]);
    }
  }
}

function errorMessage(statusCode: number): string {
  if (statusCode === 413)
    return t("register.fileTooLarge", { max: maxUploadGb });
  if (statusCode === 406) return t("register.badZip");
  return t("register.uploadFailed");
}

async function startUpload(selected: File) {
  uploading.value = true;
  progress.value = 0;
  const controller = new AbortController();
  abortController.value = controller;

  try {
    // 1. Init
    const initRes = await fetch(`${baseUrl}/api/v1/users/upload/init`, {
      method: "POST",
      body: buildAuthForm(),
      credentials: "include",
      signal: controller.signal,
    });
    if (!initRes.ok) throw new Error(`${initRes.status}`);
    const { upload_id } = (await initRes.json()) as { upload_id: string };

    // 2. Upload chunks
    const chunkCount = Math.ceil(selected.size / CHUNK_SIZE);
    for (let i = 0; i < chunkCount; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, selected.size);
      const blob = selected.slice(start, end);
      const url = `${baseUrl}/api/v1/users/upload/${upload_id}/${i}`;
      await uploadChunkWithRetry(
        url,
        blob,
        start,
        selected.size,
        controller.signal,
      );
    }

    // 3. Complete
    const completeRes = await fetch(
      `${baseUrl}/api/v1/users/upload/${upload_id}/complete`,
      {
        method: "POST",
        body: buildAuthForm(),
        credentials: "include",
        signal: controller.signal,
      },
    );
    if (!completeRes.ok) throw new Error(`${completeRes.status}`);
    const result = (await completeRes.json()) as UploadResult;
    reset();
    emit("uploaded", result);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      reset();
      return;
    }
    const status = e instanceof Error ? Number(e.message) : 0;
    $q.notify({ type: "negative", message: errorMessage(status) });
    reset();
  }
}

function cancel() {
  abortController.value?.abort();
}

function reset() {
  abortController.value = null;
  file.value = null;
  uploading.value = false;
  progress.value = 0;
}
</script>

<template>
  <div>
    <h3 class="upload-title text-h6 text-weight-semibold text-bright">
      <i18n-t keypath="register.uploadTitle">
        <template #file
          ><strong class="file-name">user_data.zip</strong></template
        >
      </i18n-t>
    </h3>
    <input
      ref="fileInputRef"
      type="file"
      accept=".zip"
      class="hidden-input"
      @change="onFileSelected"
    />
    <div class="uploader full-width" :class="{ 'uploader--dnd': dragging }">
      <!-- Header: file name + progress label -->
      <div
        v-if="file"
        class="uploader-header row no-wrap items-center q-gutter-x-sm"
      >
        <span class="text-body2 text-bright ellipsis">{{ file.name }}</span>
        <span v-if="uploading" class="text-caption text-faint">
          {{ Math.round(progress * 100) }}%
        </span>
        <q-spinner v-if="uploading" size="1rem" class="text-primary" />
        <q-space />
        <q-btn
          v-if="uploading"
          flat
          dense
          size="sm"
          :label="t('common.cancel')"
          class="text-faint"
          @click="cancel"
        />
      </div>

      <!-- Drop zone (no file selected) -->
      <div
        v-if="!file"
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
        <span class="text-body2 text-muted">{{ t("register.dropZone") }}</span>
      </div>

      <!-- Progress bar (uploading) -->
      <div v-else-if="uploading" class="upload-progress">
        <q-linear-progress
          :value="progress"
          color="primary"
          class="upload-bar"
          role="progressbar"
          :aria-valuenow="Math.round(progress * 100)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="t('register.uploadProgress')"
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

.upload-title .file-name {
  font-weight: 700;
}

.uploader {
  background: transparent;
  border: none;
  box-shadow: none;
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

.drop-zone:hover {
  border-color: var(--q-primary);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}

.drop-zone:focus-visible {
  outline: 0.125rem solid var(--q-primary);
  outline-offset: 0.125rem;
  border-color: var(--q-primary);
}

.drop-zone-icon {
  color: var(--text-faint);
  transition:
    color var(--duration-fast) ease,
    transform var(--duration-normal) cubic-bezier(0.25, 1, 0.5, 1);
}

.drop-zone:hover .drop-zone-icon {
  color: var(--q-primary);
  transform: translateY(-0.125rem);
}

.uploader--dnd .drop-zone {
  border-color: var(--q-primary);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}

.uploader--dnd .drop-zone-icon {
  color: var(--q-primary);
  transform: scale(1.1);
}

.upload-progress {
  padding: 0;
}

.upload-bar {
  border-radius: var(--radius-xs);
}

@media (prefers-reduced-motion: reduce) {
  .drop-zone-icon {
    transition: color var(--duration-fast) ease;
  }
}
</style>
