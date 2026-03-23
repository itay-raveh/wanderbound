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
  gap: 0.75rem;
}

.microsoft-btn {
  height: 2.5rem;
  padding: 0 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-color: var(--border-color);
  color: var(--text-bright);
}

.microsoft-icon {
  width: 1.25rem;
  height: 1.25rem;
  margin-right: 0.5rem;
}
</style>
