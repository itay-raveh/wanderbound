<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UploadResult } from "@/client";
import type { Provider } from "@/router";
import { useQuasar, type QUploader } from "quasar";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { symOutlinedLuggage } from "@quasar/extras/material-symbols-outlined";

const props = defineProps<{
  credential?: string;
  provider?: Provider;
}>();

const emit = defineEmits<{
  uploaded: [data: UploadResult];
}>();

const uploadUrl = `${client.getConfig().baseUrl}/api/v1/users/upload`;

const formFields = computed(() => {
  const fields: { name: string; value: string }[] = [];
  if (props.credential) fields.push({ name: "credential", value: props.credential });
  if (props.provider) fields.push({ name: "provider", value: props.provider });
  return fields;
});

const maxUploadGb = Number(import.meta.env.VITE_MAX_UPLOAD_GB) || 4;
const maxFileSize = maxUploadGb * 1024 * 1024 * 1024;

const $q = useQuasar();
const { t } = useI18n();
const uploaderRef = ref<QUploader>();

function onUploaded(info: { xhr: XMLHttpRequest }) {
  try {
    const data = JSON.parse(info.xhr.responseText) as UploadResult;
    emit("uploaded", data);
  } catch {
    onFailed();
  }
}

function onRejected() {
  $q.notify({
    type: "negative",
    message: t("register.fileTooLarge", { max: maxUploadGb }),
  });
}

function onFailed() {
  $q.notify({
    type: "negative",
    message: t("register.uploadFailed"),
  });
  uploaderRef.value?.reset();
}
</script>

<template>
  <div>
    <h3 class="upload-title text-h6 text-weight-semibold text-bright">
      <i18n-t keypath="register.uploadTitle">
        <template #file><code>user_data.zip</code></template>
      </i18n-t>
    </h3>
    <q-uploader
      ref="uploaderRef"
      accept=".zip"
      auto-upload
      :max-file-size="maxFileSize"
      class="uploader full-width"
      :url="uploadUrl"
      :form-fields="formFields"
      field-name="file"
      with-credentials
      flat
      hide-upload-btn
      @rejected="onRejected"
      @failed="onFailed"
      @uploaded="onUploaded"
    >
      <template #header="scope">
        <div v-if="scope.files.length > 0" class="uploader-header row no-wrap items-center q-gutter-x-sm">
          <span class="text-body2 text-bright ellipsis">{{ scope.files[0].name }}</span>
          <span v-if="scope.isUploading" class="text-caption text-faint">{{ scope.uploadProgressLabel }}</span>
          <q-spinner v-if="scope.isUploading" size="1rem" class="text-primary" />
        </div>
      </template>
      <template #list="scope">
        <div
          v-if="scope.files.length === 0"
          class="drop-zone column items-center justify-center"
          role="button"
          tabindex="0"
          @click="scope.pickFiles"
          @keydown.enter.prevent="scope.pickFiles"
          @keydown.space.prevent="scope.pickFiles"
        >
          <q-uploader-add-trigger />
          <q-icon :name="symOutlinedLuggage" size="2.5rem" class="drop-zone-icon text-faint" />
          <span class="text-body2 text-muted">{{ t("register.dropZone") }}</span>
        </div>
        <div v-else-if="scope.isUploading" class="upload-progress">
          <q-linear-progress :value="scope.files[0].__progress" color="primary" class="upload-bar" />
        </div>
      </template>
    </q-uploader>
  </div>
</template>

<style scoped>
.upload-title {
  margin: 0 0 var(--gap-md-lg);
}

.upload-title code {
  font-family: var(--font-mono);
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--surface) 60%, transparent);
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
  padding: 2rem var(--gap-lg);
  gap: var(--gap-md);
  cursor: pointer;
  border: 2px dashed var(--border-color);
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
  outline: 2px solid var(--q-primary);
  outline-offset: 2px;
  border-color: var(--q-primary);
}

.drop-zone-icon {
  transition:
    color var(--duration-fast) ease,
    transform var(--duration-normal) cubic-bezier(0.25, 1, 0.5, 1);
}

.drop-zone:hover .drop-zone-icon {
  color: var(--q-primary) !important;
  transform: translateY(-2px);
}

/* Quasar adds .q-uploader--dnd to the root during drag-over */
.uploader.q-uploader--dnd .drop-zone {
  border-color: var(--q-primary);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}

.uploader.q-uploader--dnd .drop-zone-icon {
  color: var(--q-primary) !important;
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
