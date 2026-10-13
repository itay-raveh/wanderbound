import * as Sentry from "@sentry/vue";
import { createPinia } from "pinia";
import { createApp } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { zPublicSettings } from "@/client/zod.gen";
import { setupSentry } from "@/plugins/sentry";

const requests = vi.hoisted(() => [] as string[]);

vi.mock("@sentry/vue", async (importOriginal) => {
  const sdk = await importOriginal<typeof import("@sentry/vue")>();
  return {
    ...sdk,
    init: (options: Parameters<typeof sdk.init>[0]) =>
      sdk.init({
        ...options,
        transport: (options) =>
          sdk.makeFetchTransport(options, async (_url, init) => {
            requests.push(await new Response(init?.body).text());
            return new Response(null, { status: 200 });
          }),
      }),
  };
});

it("keeps IP inference disabled in outgoing Sentry events", async () => {
  document.cookie = "private_album=travel-secret";
  const router = createRouter({ history: createMemoryHistory(), routes: [] });

  try {
    setupSentry(
      createApp({}),
      router,
      createPinia(),
      zPublicSettings.parse({
        ENVIRONMENT: "production",
        PUBLIC_SENTRY_DSN: "https://public@example.invalid/1",
        SENTRY_TRACES_SAMPLE_RATE: 0,
      }),
    );
    Sentry.setUser({ id: "42" });
    Sentry.captureMessage("privacy-regression");
    await Sentry.flush(2000);

    const events = requests.flatMap((body) =>
      body
        .split("\n")
        .filter((line) => line.startsWith("{"))
        .map((line) => JSON.parse(line)),
    );
    const event = events.find((value) => value.message === "privacy-regression");
    expect(event).toBeDefined();
    expect(event.sdk.settings.infer_ip).toBe("never");
    expect(event.user).toEqual({ id: "42" });
    expect(event.request?.cookies).toBeUndefined();
    expect(requests.join("\n")).not.toContain("travel-secret");
  } finally {
    await Sentry.close();
    Sentry.setUser(null);
    document.cookie = "private_album=; Max-Age=0";
  }
});
