import { quasar, transformAssetUrls } from "@quasar/vite-plugin";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import path from "path";
import { defineConfig } from "vite";

import { sentryRelease } from "./src/sentryRelease";

const version = process.env.APP_VERSION;
const release = sentryRelease(version);
const sentryApplicationKey = "wanderbound";
const envDir = path.resolve(__dirname, "..");

export default defineConfig({
  define: {
    APP_VERSION: JSON.stringify(version),
  },
  envDir,
  server: {
    host: true,
    allowedHosts: true,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  plugins: [
    vue({
      template: { transformAssetUrls },
    }),
    quasar({
      sassVariables: path.resolve(__dirname, "src/quasar-variables.sass"),
    }),
    VueI18nPlugin({
      include: [path.resolve(__dirname, "src/i18n/locales/**")],
    }),
    sentryVitePlugin({
      applicationKey: sentryApplicationKey,
      release: {
        name: release,
        setCommits: false,
        create: false,
        finalize: false,
        deploy: false,
      },
      telemetry: false,
      sourcemaps: {
        disable: "disable-upload",
      },
    }),
  ],
  resolve: {
    dedupe: ["@mapbox/mapbox-gl-supported"],
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@fonts": path.resolve(__dirname, "fonts.json"),
    },
  },
  build: {
    sourcemap: "hidden",
    chunkSizeWarningLimit: 1800, // mapbox-gl is ~1.7MB and cannot be tree-shaken or split
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        redirect: path.resolve(__dirname, "redirect.html"),
      },
      output: {
        manualChunks: {
          mapbox: ["mapbox-gl"],
          sentry: ["@sentry/vue"],
          turf: [
            "@turf/along",
            "@turf/distance",
            "@turf/helpers",
            "@turf/length",
            "@turf/nearest-point-on-line",
          ],
        },
      },
    },
  },
});
