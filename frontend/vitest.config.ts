import { quasar, transformAssetUrls } from "@quasar/vite-plugin";
import vue from "@vitejs/plugin-vue";
import VueI18nPlugin from "@intlify/unplugin-vue-i18n/vite";
import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({
      sassVariables: path.resolve(__dirname, "src/quasar-variables.sass"),
    }),
    VueI18nPlugin({
      include: [path.resolve(__dirname, "src/i18n/locales/**")],
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@fonts": path.resolve(__dirname, "fonts.json"),
    },
  },
  define: {
    APP_VERSION: JSON.stringify("0.0.0-test"),
  },
  test: {
    environment: "happy-dom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts"],
    globals: true,
  },
});
