import { quasar, transformAssetUrls } from "@quasar/vite-plugin";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import path from "path";
import { defineConfig } from "vite";
import { version } from "./package.json";

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  envDir: path.resolve(__dirname, ".."),
  server: {
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
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_FRONTEND_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      telemetry: false,
      sourcemaps: {
        filesToDeleteAfterUpload: ["./dist/**/*.map"],
      },
    }),
  ],
  resolve: {
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
            "@turf/simplify",
          ],
        },
      },
    },
  },
});
