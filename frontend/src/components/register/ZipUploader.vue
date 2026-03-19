<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UserCreated } from "@/client";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import RegisterStep from "./RegisterStep.vue";

const emit = defineEmits<{
  uploaded: [data: UserCreated];
}>();

const uploadUrl = `${client.getConfig().baseUrl}/api/v1/users`;

const $q = useQuasar();
const { t } = useI18n();

function onUploaded(info: { xhr: XMLHttpRequest }) {
  const data = JSON.parse(info.xhr.responseText) as UserCreated;
  emit("uploaded", data);
}

function onFailed() {
  $q.notify({
    type: "negative",
    message: t("register.uploadFailed"),
  });
}
</script>

<template>
  <RegisterStep :number="2">
    <template #title>
      <i18n-t keypath="register.uploadTitle">
        <template #file><code>user_data.zip</code></template>
      </i18n-t>
    </template>
    <q-uploader
      accept=".zip"
      auto-upload
      class="uploader full-width"
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
