import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

import { afterEach, describe, expect, it, vi } from "vitest";

const sentry = {
  browserTracingIntegration: vi.fn(() => ({})),
  createSentryPiniaPlugin: vi.fn(() => ({})),
  feedbackIntegration: vi.fn(() => ({})),
  init: vi.fn(),
  replayIntegration: vi.fn(() => ({})),
  thirdPartyErrorFilterIntegration: vi.fn(() => ({})),
};

vi.mock("@sentry/vue", () => sentry);

async function setupWith(config: Record<string, string>) {
  vi.doMock("@/config", () => ({ frontendConfig: config }));
  const { setupSentry } = await import("@/plugins/sentry");
  const pinia = { use: vi.fn() } as unknown as Pinia;
  setupSentry({} as App, {} as Router, pinia);
  return pinia;
}

afterEach(() => {
  vi.clearAllMocks();
  vi.resetModules();
});

describe("Sentry startup configuration", () => {
  it.each([
    ["local", "https://public@example.test/1"],
    ["production", ""],
  ])(
    "stays disabled for environment %s and DSN %s",
    async (environment, dsn) => {
      await setupWith({
        VITE_ENVIRONMENT: environment,
        VITE_SENTRY_DSN: dsn,
        VITE_SENTRY_TRACES_SAMPLE_RATE: "0.5",
      });

      expect(sentry.init).not.toHaveBeenCalled();
    },
  );

  it("uses the runtime target, image release, and current sampling fallback", async () => {
    await setupWith({
      VITE_ENVIRONMENT: "production",
      VITE_SENTRY_DSN: "https://public@example.test/1",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "invalid",
    });

    expect(sentry.init).toHaveBeenCalledOnce();
    const options = sentry.init.mock.calls[0]?.[0];
    expect(options).toMatchObject({
      dsn: "https://public@example.test/1",
      environment: "production",
      release: "wanderbound@0.0.0-test",
    });
    expect(options?.tracesSampler({})).toBe(0.1);
  });
});
