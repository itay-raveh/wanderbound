import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { Loading, LoadingBar, Notify, Quasar } from "quasar";
import { createApp } from "vue";

// Import icon libraries
import "@quasar/extras/material-icons/material-icons.css";
import "@quasar/extras/material-symbols-outlined/material-symbols-outlined.css";

// Import Quasar css
import "quasar/src/css/index.sass";

// Import Mapbox CSS
import "mapbox-gl/dist/mapbox-gl.css";

// Import shared animations
import "@/styles/animations.css";

import App from "./App.vue";
import router from "./router";

import { client } from "@/client/client.gen";

import { initDarkMode } from "@/composables/useDarkMode";

client.setConfig({
  baseUrl: import.meta.env.VITE_BACKEND_URL,
  credentials: "include",
});

const app = createApp(App);

app.use(createPinia());
app.use(PiniaColada);
app.use(router);
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
  plugins: { Notify, LoadingBar, Loading },
});

initDarkMode();
app.mount("#app");
