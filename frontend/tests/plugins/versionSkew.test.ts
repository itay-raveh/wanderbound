import { createClient } from "@/client/client";
import { setupVersionSkewRecovery } from "@/plugins/versionSkew";

const responseHeaders = {
  "Content-Type": "application/json",
  "X-Wanderbound-Version": "1.11.0",
};

it("reloads and rejects an API response from an incompatible release", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ pages: [{ kind: "grid", media: [] }] }), {
        headers: responseHeaders,
      }),
    ),
  );
  const reload = vi.fn();
  const client = createClient({
    baseUrl: "https://example.invalid",
    fetch,
    throwOnError: true,
  });
  setupVersionSkewRecovery(client, "1.10.0", reload);

  await expect(client.get({ url: "/api/v1/albums/1/steps" })).rejects.toThrow(
    "Frontend 1.10.0 cannot use API 1.11.0; reloading",
  );
  expect(reload).toHaveBeenCalledOnce();
});

it("accepts responses from an unversioned local API", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  const reload = vi.fn();
  const client = createClient({
    baseUrl: "https://example.invalid",
    fetch,
    throwOnError: true,
  });
  setupVersionSkewRecovery(client, "1.11.0", reload);

  await expect(client.get({ url: "/api/v1/health" })).resolves.toBeDefined();
  expect(reload).not.toHaveBeenCalled();
});
