<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UserCreated } from "@/client";
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
      class="uploader full-width"
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
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--surface) 50%, transparent);
  transition:
    border-color var(--duration-fast) ease,
    background var(--duration-fast) ease;
}

.uploader:hover {
  border-color: color-mix(in srgb, var(--q-primary) 50%, transparent);
  background: color-mix(in srgb, var(--q-primary) 5%, transparent);
}
</style>
