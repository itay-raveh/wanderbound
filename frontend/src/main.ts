import { createPinia } from "pinia";
import { Loading, LoadingBar, Notify, Quasar } from "quasar";
import { createApp } from "vue";

// Import icon libraries
import "@quasar/extras/material-icons/material-icons.css";
import "@quasar/extras/material-symbols-outlined/material-symbols-outlined.css";

// Import Quasar css
import "quasar/src/css/index.sass";

import App from "./App.vue";
import router from "./router";

import { client } from "./api/client.gen";

client.setConfig({ withCredentials: true });

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(Quasar, {
  config: {
    dark: true,
    loading: {},
    loadingBar: {
      color: "info",
    },
    brand: {
      primary: "#0063d1",
      secondary: "#0802b3",
      accent: "#2d254c",
      "dark-page": "#1a1a2e",
      dark: "#252540",
      positive: "#21BA45",
      negative: "#C10015",
      info: "#31CCEC",
      warning: "#F2C037",
    },
  },
  plugins: { Notify, LoadingBar, Loading },
});

app.mount("#app");
