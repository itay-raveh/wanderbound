<script lang="ts" setup>
import { client } from "@/client/client.gen";
import type { UploadResult } from "@/client";
import type { Provider } from "@/router";
import { useQuasar } from "quasar";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import RegisterStep from "./RegisterStep.vue";

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

function onUploaded(info: { xhr: XMLHttpRequest }) {
  const data = JSON.parse(info.xhr.responseText) as UploadResult;
  emit("uploaded", data);
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
      :max-file-size="maxFileSize"
      class="uploader full-width"
      :url="uploadUrl"
      :form-fields="formFields"
      field-name="file"
      with-credentials
      bordered
      flat
      @rejected="onRejected"
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
