const SENTRY_PACKAGE = "wanderbound";

export function sentryRelease(version: string | undefined): string | undefined {
  if (!version) return undefined;
  return `${SENTRY_PACKAGE}@${version.replace(/^v/, "")}`;
}
