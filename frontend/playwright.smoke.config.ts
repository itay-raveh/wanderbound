import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

export default defineConfig({
  ...baseConfig,
  timeout: 60_000,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  testDir: "./smoke",
  webServer: undefined,
});
