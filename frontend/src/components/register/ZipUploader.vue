<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UserCreated } from "@/client/types.gen";
import { useQuasar } from "quasar";
import RegisterStep from "./RegisterStep.vue";

const emit = defineEmits<{
  uploaded: [data: UserCreated];
}>();

const uploadUrl = `${client.getConfig().baseUrl}/api/v1/users`;

const $q = useQuasar();

function onUploaded(info: { xhr: XMLHttpRequest }) {
  const data = JSON.parse(info.xhr.responseText) as UserCreated;
  emit("uploaded", data);
}

function onFailed() {
  $q.notify({
    type: "negative",
    message: "Upload failed. Please try again.",
  });
}
</script>

<template>
  <RegisterStep :number="2">
    <template #title>Upload your <code>user_data.zip</code></template>
    <q-uploader
      accept=".zip"
      auto-upload
      class="uploader"
      label="Drop .zip file here or click to browse"
      :url="uploadUrl"
      field-name="file"
      with-credentials
      bordered
      flat
      @failed="onFailed"
      @uploaded="onUploaded"
    />
  </RegisterStep>
</template>

<style scoped>
.uploader {
  width: 100%;
  border-radius: 0.625rem;
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.uploader:hover {
  border-color: color-mix(in srgb, var(--q-primary) 50%, transparent);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}

.uploader :deep(.q-uploader__header) {
  background: transparent;
  color: var(--text-faint);
  border-bottom: none;
  padding: 0.75rem 1rem;
}

.uploader :deep(.q-uploader__list) {
  padding: 0.5rem 1rem;
}

.uploader :deep(.q-uploader__subtitle) {
  color: var(--text-faint);
}

.uploader :deep(.q-uploader__title) {
  font-size: 0.8125rem;
  font-weight: 500;
}
</style>
