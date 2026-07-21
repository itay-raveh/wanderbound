import { quasar, transformAssetUrls } from "@quasar/vite-plugin";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import path from "path";
import { defineConfig } from "vite";

const sentryApplicationKey = "wanderbound";
const apiProxyUrl = process.env.API_PROXY_URL ?? "http://localhost:8000";

export default defineConfig({
    server: {
      host: true,
      allowedHosts: true,
      proxy: {
        "/api": apiProxyUrl,
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
        telemetry: false,
        sourcemaps: {
          disable: "disable-upload",
        },
        release: {
          inject: false,
          create: false,
          finalize: false,
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
