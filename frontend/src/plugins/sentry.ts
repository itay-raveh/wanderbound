import * as Sentry from "@sentry/vue";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";

import { frontendConfig } from "@/config";
import { sentryRelease } from "@/sentryRelease";

const PRELOAD_ERROR_PATTERNS = [
  "Failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "Importing a module script failed",
];
const DEFAULT_SENTRY_TRACES_SAMPLE_RATE = 0.1;
const SENTRY_APPLICATION_KEY = "wanderbound";
const SENTRY_TRACE_PROPAGATION_TARGETS = [/^\/api\//];
const PRESIGNED_URL_PARAMETER = "x-amz-signature";

export function isSensitiveUploadUrl(value: unknown): boolean {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value, window.location.origin);
    return [...url.searchParams.keys()].some(
      (key) => key.toLowerCase() === PRESIGNED_URL_PARAMETER,
    );
  } catch {
    return false;
  }
}

export function setupSentry(app: App, router: Router, pinia: Pinia): void {
  if (!sentryEnabled()) return;

  const tracesSampleRate = sentryTracesSampleRate();
  Sentry.init({
    app,
    dsn: frontendConfig.VITE_SENTRY_DSN,
    environment: frontendConfig.VITE_ENVIRONMENT,
    release: sentryRelease(APP_VERSION),
    integrations: [
      Sentry.feedbackIntegration({
        autoInject: true,
        colorScheme: "system",
        showBranding: true,
        showName: false,
        showEmail: true,
        isEmailRequired: false,
        enableScreenshot: true,
      }),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
        beforeAddRecordingEvent(event) {
          const payload = event.data.payload as { description?: unknown };
          return event.data.tag === "performanceSpan" &&
            isSensitiveUploadUrl(payload.description)
            ? null
            : event;
        },
      }),
      Sentry.browserTracingIntegration({
        router,
        shouldCreateSpanForRequest: (url) => !isSensitiveUploadUrl(url),
      }),
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
    beforeBreadcrumb(breadcrumb) {
      return isSensitiveUploadUrl(breadcrumb.data?.url) ? null : breadcrumb;
    },
    beforeSend(event) {
      const message = event.exception?.values?.[0]?.value ?? "";
      if (PRELOAD_ERROR_PATTERNS.some((p) => message.includes(p))) return null;
      event.breadcrumbs = event.breadcrumbs?.filter(
        (breadcrumb) => !isSensitiveUploadUrl(breadcrumb.data?.url),
      );
      return event;
    },
  });
  pinia.use(Sentry.createSentryPiniaPlugin());
}

function sentryEnabled(): boolean {
  return (
    frontendConfig.VITE_ENVIRONMENT === "production" &&
    Boolean(frontendConfig.VITE_SENTRY_DSN)
  );
}

function sentryTracesSampleRate(): number {
  const value = Number(
    frontendConfig.VITE_SENTRY_TRACES_SAMPLE_RATE ??
      DEFAULT_SENTRY_TRACES_SAMPLE_RATE,
  );
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    return DEFAULT_SENTRY_TRACES_SAMPLE_RATE;
  }
  return value;
}
