import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import * as Sentry from "@sentry/vue";
import { Lang, Loading, LoadingBar, Meta, Notify, Quasar } from "quasar";
import { createApp } from "vue";

import vue3GoogleLogin from "vue3-google-login";

import i18n from "@/i18n";
import { applyLocale } from "@/composables/useLocale";

// Self-hosted fonts with font-display: block.
// Guarantees fonts are loaded before rendering (critical for PDF generation).
import "@/styles/fonts.css";

// Quasar's built-in components (q-uploader, q-select, etc.) reference
// material-icons by string name, so the font CSS must stay loaded.
import "@quasar/extras/material-icons/material-icons.css";

import "quasar/src/css/index.sass";
import "@/styles/quasar-overrides.scss";
import "@/styles/animations.css";

import App from "./App.vue";
import router from "./router";

import { client } from "@/client/client.gen";

client.setConfig({
  baseUrl: "",
  credentials: "include",
});

const app = createApp(App);
const pinia = createPinia();

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    release: __APP_VERSION__,
    integrations: [Sentry.replayIntegration()],
    tracesSampleRate: 0,
    replaysOnErrorSampleRate: 1.0,
  });
  pinia.use(Sentry.createSentryPiniaPlugin());
}

app.use(pinia);
app.use(PiniaColada);
app.use(router);
app.use(i18n);
app.use(vue3GoogleLogin, {
  clientId: import.meta.env.VITE_GOOGLE_CLIENT_ID,
});
app.use(Quasar, {
  config: {
    loading: {},
    loadingBar: {
      color: "info",
    },
    brand: {
      primary: "#0063d1",
      secondary: "#0802b3",
      accent: "#2d254c",
      "dark-page": "#1E1E2E",
      dark: "#252540",
      positive: "#21BA45",
      negative: "#C10015",
      info: "#31CCEC",
      warning: "#F2C037",
    },
  },
  plugins: { Meta, Notify, LoadingBar, Loading },
});

// Dark mode: reactive pref bridged to Quasar Dark plugin.
import { useDarkMode } from "@/composables/useDarkMode";
useDarkMode();

// Browser locale detection (covers register page before user exists).
// Awaited so the correct lang pack (incl. RTL direction) is active on first paint.
try {
  await applyLocale(Lang.getLocale() ?? "en-US");
} catch {
  /* falls back to en */
}

app.mount("#app");
