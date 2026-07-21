import { createApp } from "vue";

vi.unmock("vue3-google-login");

import { setupGoogleLogin } from "@/plugins/googleLogin";

it("handles failures while loading the Google Identity Services library", async () => {
  const handleLoadError = vi.fn();
  const app = createApp({});
  let googleScript: HTMLScriptElement | undefined;
  const appendChild = vi.spyOn(document.head, "appendChild");
  appendChild.mockImplementation(function <T extends Node>(node: T): T {
    if (node instanceof HTMLScriptElement) {
      googleScript = node;
      queueMicrotask(() => node.dispatchEvent(new Event("error")));
    }
    return node;
  });

  setupGoogleLogin(app, "client-id", handleLoadError);

  expect(googleScript?.src).toBe(
    "https://accounts.google.com/gsi/client",
  );

  await vi.waitFor(() => {
    expect(handleLoadError).toHaveBeenCalledWith(
      "Failed to load the Google 3P Authorization JavaScript Library.",
    );
  });
  appendChild.mockRestore();
});
