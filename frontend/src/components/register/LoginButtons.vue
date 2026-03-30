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
    <!-- Google: invisible real button on top captures clicks, custom visual beneath -->
    <div class="auth-btn-wrapper">
      <span class="auth-btn">
        <img src="/google-logo.svg" alt="" class="auth-btn-icon" />
        <span class="auth-btn-text">{{ t("login.signInGoogle") }}</span>
      </span>
      <GoogleLogin
        :callback="(r: CallbackTypes.CredentialPopupResponse) => emit('google', r)"
        :button-config="{ theme: 'outline', size: 'large', shape: 'pill', width: '260' }"
        class="auth-btn-overlay"
      />
    </div>

    <button class="auth-btn" @click="emit('microsoft')">
      <img src="/microsoft-logo.svg" alt="" class="auth-btn-icon" />
      <span class="auth-btn-text">{{ t("login.signInMicrosoft") }}</span>
    </button>
  </div>
</template>

<style scoped>
.login-buttons {
  gap: var(--gap-md-lg);
}

/* Shared base for both providers */
.auth-btn {
  all: unset;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16.25rem;
  height: 2.75rem;
  padding: 0 1.25rem;
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 600;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition:
    background var(--duration-fast),
    box-shadow var(--duration-fast),
    transform var(--duration-fast);
}

.auth-btn:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 2px;
}

/* Google wrapper: show focus ring when the iframe overlay receives keyboard focus */
.auth-btn-wrapper:has(:focus-visible) > .auth-btn {
  outline: 2px solid var(--q-primary);
  outline-offset: 2px;
}

.auth-btn:active {
  transform: scale(0.98);
}

/* Both providers: same visual weight */
.auth-btn {
  color: var(--text-bright);
  background: var(--surface);
  border: 1.5px solid var(--border-color);
  box-shadow: var(--shadow-sm);
}

.auth-btn:hover,
.auth-btn-wrapper:hover > .auth-btn {
  background: color-mix(in srgb, var(--q-primary) 8%, var(--surface));
  border-color: var(--q-primary);
  box-shadow: var(--shadow-md);
}

.auth-btn-text {
  flex: 1;
  text-align: center;
}

.auth-btn-icon {
  width: 1.125rem;
  height: 1.125rem;
  flex-shrink: 0;
  margin-inline-end: 0.5rem;
}

/* Google overlay: invisible iframe on top captures clicks */
.auth-btn-wrapper {
  position: relative;
  width: 16.25rem;
  height: 2.75rem;
}

.auth-btn-wrapper > .auth-btn {
  position: absolute;
  inset: 0;
}

.auth-btn-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  opacity: 0;
  overflow: hidden;
}

.auth-btn-overlay :deep(.g-btn-wrapper) {
  width: 100%;
  height: 100%;
}
</style>
