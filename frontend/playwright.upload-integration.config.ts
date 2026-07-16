import { defineConfig } from "@playwright/test";

const baseURL = process.env.DIRECT_UPLOAD_BASE_URL;
if (!baseURL) throw new Error("DIRECT_UPLOAD_BASE_URL must be set");

export default defineConfig({
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  testDir: "./integration",
  outputDir: "./integration/test-results",
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "line",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
