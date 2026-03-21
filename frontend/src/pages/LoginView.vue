<script lang="ts" setup>
import { authGoogle } from "@/client";
import { useQuasar } from "quasar";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { type CallbackTypes } from "vue3-google-login";
import { CREDENTIAL_KEY } from "@/router";

const { t } = useI18n();
const router = useRouter();
const $q = useQuasar();

async function onSuccess(response: CallbackTypes.CredentialPopupResponse) {
  try {
    const { data: user } = await authGoogle({ body: { credential: response.credential } });
    if (user) {
      await router.push({ name: "editor" });
    } else {
      sessionStorage.setItem(CREDENTIAL_KEY, response.credential);
      await router.push({ name: "upload" });
    }
  } catch {
    $q.notify({ type: "negative", message: t("login.signInFailed") });
  }
}
</script>

<template>
  <q-page class="login-page column no-wrap flex-center">
    <q-img src="/logo.svg" class="login-logo fade-up" />
    <h1 class="login-brand text-h4 text-bright text-weight-bold fade-up">
      {{ t("brand") }}
    </h1>
    <p class="login-tagline text-subtitle1 text-muted fade-up">
      {{ t("register.tagline") }}
    </p>
    <div class="login-button fade-up">
      <GoogleLogin :callback="onSuccess" />
    </div>
  </q-page>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  background: var(--page-gradient);
}

.login-logo {
  width: 5.5rem;
  height: 5.5rem;
}

.login-brand {
  margin: 1.25rem 0 0;
}

.login-tagline {
  margin: 0.5rem 0 0;
}

.login-button {
  margin-top: 2.5rem;
  animation-delay: 0.1s;
}

.login-brand,
.login-tagline {
  text-align: center;
}
</style>
