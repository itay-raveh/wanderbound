import { createPinia } from "pinia";
import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import type { Settings } from "@/config";

const sentry = vi.hoisted(() => ({
  browserTracingIntegration: vi.fn(() => ({})),
  createSentryPiniaPlugin: vi.fn(() => () => undefined),
  feedbackIntegration: vi.fn(() => ({})),
  init: vi.fn(),
  replayIntegration: vi.fn(() => ({})),
  thirdPartyErrorFilterIntegration: vi.fn(() => ({})),
}));

vi.mock("@sentry/vue", () => sentry);
vi.mock("@/plugins/versionSkew", () => ({ BUILD_VERSION: "1.8.3" }));

import { isSensitiveUploadUrl, setupSentry } from "@/plugins/sentry";

it("recognizes upload bearer credentials without treating ordinary URLs as sensitive", () => {
  expect(
    isSensitiveUploadUrl(
      "https://objects.example/uploads/file.zip?X-Amz-Date=now&X-Amz-Signature=secret",
    ),
  ).toBe(true);
  expect(
    isSensitiveUploadUrl("/api/v1/users/uploads/id?key=uploads%2Fid.zip"),
  ).toBe(false);
});

it("attributes events to the frontend build instead of the server version", () => {
  const app = createApp({});
  const router = createRouter({ history: createWebHistory(), routes: [] });
  const pinia = createPinia();
  const settings = {
    APP_VERSION: "1.10.0",
    ENVIRONMENT: "production",
    PUBLIC_SENTRY_DSN: "https://public@example.invalid/1",
    SENTRY_TRACES_SAMPLE_RATE: 0.1,
  } as Settings;

  setupSentry(app, router, pinia, settings);

  expect(sentry.init).toHaveBeenCalledWith(
    expect.objectContaining({ release: "wanderbound@1.8.3" }),
  );
});
