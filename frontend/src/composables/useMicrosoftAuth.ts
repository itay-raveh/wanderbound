import { PublicClientApplication } from "@azure/msal-browser";

const clientId = import.meta.env.VITE_MICROSOFT_CLIENT_ID;

let msalPromise: Promise<PublicClientApplication> | null = null;

function getInstance(): Promise<PublicClientApplication> {
  if (!msalPromise) {
    msalPromise = (async () => {
      const instance = new PublicClientApplication({
        auth: {
          clientId,
          authority: "https://login.microsoftonline.com/common",
          redirectUri: "/redirect.html",
        },
        cache: { cacheLocation: "sessionStorage" },
      });
      await instance.initialize();
      return instance;
    })();
  }
  return msalPromise;
}

/** Clear MSAL's local token cache (call on app logout). */
export async function clearMsalCache(): Promise<void> {
  if (!msalPromise) return;
  const instance = await msalPromise;
  await instance.clearCache();
}

export async function microsoftLogin(): Promise<string> {
  const instance = await getInstance();
  const result = await instance.loginPopup({
    scopes: ["openid", "profile"],
    prompt: "select_account",
  });
  return result.idToken;
}
