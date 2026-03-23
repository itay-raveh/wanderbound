<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { type CallbackTypes } from "vue3-google-login";

const { t } = useI18n();

const emit = defineEmits<{
  google: [response: CallbackTypes.CredentialPopupResponse];
  microsoft: [];
}>();
</script>

<template>
  <div class="login-buttons column no-wrap items-center">
    <GoogleLogin :callback="(r: CallbackTypes.CredentialPopupResponse) => emit('google', r)" />
    <q-btn
      unelevated
      no-caps
      outline
      class="microsoft-btn"
      @click="emit('microsoft')"
    >
      <img src="/microsoft-logo.svg" alt="" class="microsoft-icon" />
      {{ t("login.signInMicrosoft") }}
    </q-btn>
  </div>
</template>

<style scoped>
.login-buttons {
  gap: var(--gap-md-lg);
}

.microsoft-btn {
  min-height: 2.75rem;
  padding: 0 var(--gap-md-lg);
  font-size: var(--type-sm);
  font-weight: 500;
  border-color: var(--border-color);
  color: var(--text-bright);
}

.microsoft-icon {
  width: 1.25rem;
  height: 1.25rem;
  margin-inline-end: var(--gap-md);
}
</style>
