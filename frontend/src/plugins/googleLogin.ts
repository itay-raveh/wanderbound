import type { App } from "vue";
import vue3GoogleLogin from "vue3-google-login";

type GoogleLoginLoadErrorHandler = (error: unknown) => void;

export function setupGoogleLogin(
  app: App,
  clientId: string | undefined,
  handleLoadError: GoogleLoginLoadErrorHandler = () => undefined,
): void {
  if (!clientId) return;
  app.use(vue3GoogleLogin, { clientId, error: handleLoadError });
}
