import type { Client } from "@/client/client";

const VERSION_HEADER = "X-Wanderbound-Version";
export const BUILD_VERSION = import.meta.env.VITE_APP_VERSION || undefined;

export function setupVersionSkewRecovery(
  client: Client,
  frontendVersion = BUILD_VERSION,
  reload = () => window.location.reload(),
): void {
  if (!frontendVersion) return;

  client.interceptors.response.use((response) => {
    const serverVersion = response.headers.get(VERSION_HEADER);
    if (!serverVersion || serverVersion === frontendVersion) return response;

    reload();
    throw new Error(
      `Frontend ${frontendVersion} cannot use API ${serverVersion}; reloading`,
    );
  });
}
