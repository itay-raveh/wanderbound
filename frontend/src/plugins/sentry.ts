import * as Sentry from "@sentry/vue";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

const PRELOAD_ERROR_PATTERNS = [
  "Failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "Importing a module script failed",
];
const DEFAULT_SENTRY_TRACES_SAMPLE_RATE = 0.1;
const SENTRY_APPLICATION_KEY = "wanderbound";
const SENTRY_TRACE_PROPAGATION_TARGETS = [/^\/api\//];

export function setupSentry(app: App, router: Router, pinia: Pinia): void {
  if (!sentryEnabled()) return;

  const tracesSampleRate = sentryTracesSampleRate();
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    release: APP_VERSION,
    integrations: [
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
      Sentry.browserTracingIntegration({ router }),
      Sentry.thirdPartyErrorFilterIntegration({
        filterKeys: [SENTRY_APPLICATION_KEY],
        behaviour: "apply-tag-if-exclusively-contains-third-party-frames",
      }),
    ],
    tracesSampler(samplingContext) {
      if (typeof samplingContext.parentSampled === "boolean") {
        return samplingContext.parentSampled;
      }
      return tracesSampleRate;
    },
    tracePropagationTargets: SENTRY_TRACE_PROPAGATION_TARGETS,
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,
    beforeSend(event) {
      const message = event.exception?.values?.[0]?.value ?? "";
      if (PRELOAD_ERROR_PATTERNS.some((p) => message.includes(p))) return null;
      return event;
    },
  });
  pinia.use(Sentry.createSentryPiniaPlugin());
}

function sentryEnabled(): boolean {
  return import.meta.env.PROD && Boolean(import.meta.env.VITE_SENTRY_DSN);
}

function sentryTracesSampleRate(): number {
  const value = Number(
    import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ??
      DEFAULT_SENTRY_TRACES_SAMPLE_RATE,
  );
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    return DEFAULT_SENTRY_TRACES_SAMPLE_RATE;
  }
  return value;
}
