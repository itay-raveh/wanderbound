import type { RuntimeSettings } from "@/config";
import { isSensitiveUploadUrl, setupSentry } from "@/plugins/sentry";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

const sentry = vi.hoisted(() => ({
  init: vi.fn(),
  piniaPlugin: vi.fn(),
}));

vi.mock("@sentry/vue", () => ({
  init: sentry.init,
  createSentryPiniaPlugin: () => sentry.piniaPlugin,
  feedbackIntegration: () => ({}),
  replayIntegration: () => ({}),
  browserTracingIntegration: () => ({}),
  thirdPartyErrorFilterIntegration: () => ({}),
}));

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

it("uses startup settings and a package SemVer release", () => {
  const use = vi.fn();
  const pinia = { use } as unknown as Pinia;
  const settings = {
    ENVIRONMENT: "production",
    APP_VERSION: "v1.7.0",
    PUBLIC_SENTRY_DSN: "https://public@example.invalid/1",
    SENTRY_TRACES_SAMPLE_RATE: 0.25,
  } as RuntimeSettings;

  setupSentry({} as App, {} as Router, pinia, settings);

  expect(sentry.init).toHaveBeenCalledWith(
    expect.objectContaining({
      dsn: settings.PUBLIC_SENTRY_DSN,
      environment: "production",
      release: "wanderbound@1.7.0",
    }),
  );
  expect(use).toHaveBeenCalledWith(sentry.piniaPlugin);
});
