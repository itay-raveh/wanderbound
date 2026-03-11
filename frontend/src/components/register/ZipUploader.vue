<script lang="ts" setup>
import { client } from "@/client/client.gen";
import { useQuasar } from "quasar";
import { useRouter } from "vue-router";
import RegisterStep from "./RegisterStep.vue";

const uploadUrl = `${client.getConfig().baseUrl}/api/v1/users`;

const router = useRouter();
const $q = useQuasar();

async function onUploaded() {
  await router.push("/");
}

function onFailed(info: { xhr: XMLHttpRequest }) {
  const status = info.xhr?.status;
  $q.notify({
    type: "negative",
    message: `Upload failed. ${status ? `Server returned ${status}.` : "Please try again"}`,
  });
}
</script>

<template>
  <RegisterStep :number="2" title="Upload your <code>user_data.zip</code>">
    <q-uploader
      accept=".zip"
      auto-upload
      class="uploader"
      field-name="file"
      label="Drop .zip file here or click to browse"
      :url="uploadUrl"
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
