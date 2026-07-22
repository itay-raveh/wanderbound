import * as Sentry from "@sentry/vue";
import type { Pinia } from "pinia";
import type { App } from "vue";
import type { Router } from "vue-router";
import type { Settings } from "@/config";

const PRELOAD_ERROR_PATTERNS = [
  "Failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "Importing a module script failed",
];
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

export function setupSentry(
  app: App,
  router: Router,
  pinia: Pinia,
  settings: Settings,
): void {
  if (!sentryEnabled(settings)) return;

  Sentry.init({
    app,
    dsn: settings.PUBLIC_SENTRY_DSN ?? undefined,
    environment: settings.ENVIRONMENT,
    release: settings.APP_VERSION
      ? `wanderbound@${settings.APP_VERSION}`
      : undefined,
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
      return settings.SENTRY_TRACES_SAMPLE_RATE;
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

function sentryEnabled(settings: Settings): boolean {
  return (
    settings.ENVIRONMENT === "production" &&
    Boolean(settings.PUBLIC_SENTRY_DSN)
  );
}
