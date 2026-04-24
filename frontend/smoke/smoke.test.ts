import { test, expect } from "@playwright/test";

test.describe("Stack smoke tests", () => {
  test("backend is healthy", async ({ request }) => {
    const resp = await request.get("/api/v1/health");
    expect(resp.ok()).toBe(true);
    const body = await resp.json();
    expect(body.db).toBe(true);
    expect(body.disk).toBe(true);
    expect(body.playwright).toBe(true);
  });

  test("frontend loads with security headers", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    const resp = await page.goto("/");
    await expect(page).toHaveTitle(/wanderbound/i);
    expect(errors).toEqual([]);

    expect(resp).not.toBeNull();
    const headers = resp!.headers();
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["strict-transport-security"]).toContain("max-age=");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
  });

  test("static assets have immutable cache headers", async ({ page }) => {
    const assetResponse = page.waitForResponse((r) =>
      r.url().includes("/assets/"),
    );
    await page.goto("/");
    const resp = await assetResponse;
    expect(resp.ok()).toBe(true);
    expect(resp.headers()["cache-control"]).toContain("immutable");
  });

  test("demo user can reach editor and stream SSE", async ({ page }) => {
    const resp = await page.request.post("/api/v1/users/demo");
    expect(resp.status(), `demo responded ${resp.status()}: ${await resp.text()}`).toBe(200);
    const { user } = await resp.json();
    expect(user.album_ids.length).toBeGreaterThan(0);

    // /upload is where the route guard sends authenticated users until
    // is_processed flips true. Going straight to /editor pre-processing
    // would 404 on album queries.
    await page.goto("/upload");

    const firstEvent = await page.evaluate(async () => {
      return new Promise<string>((resolve, reject) => {
        const timeout = setTimeout(() => { es.close(); reject(new Error("SSE timeout")); }, 10_000);
        const es = new EventSource("/api/v1/users/process");
        es.onmessage = (e) => {
          clearTimeout(timeout);
          es.close();
          resolve(e.data);
        };
        es.onerror = () => {
          clearTimeout(timeout);
          es.close();
          reject(new Error("SSE connection failed"));
        };
      });
    });

    const event = JSON.parse(firstEvent);
    expect(event).toHaveProperty("type");

    await page.waitForFunction(
      async () => {
        const r = await fetch("/api/v1/auth/state", { credentials: "include" });
        const s = await r.json();
        return s.state === "authenticated" && s.user?.is_processed === true;
      },
      null,
      { timeout: 60_000 },
    );

    await page.goto("/editor");
    await page.waitForURL(/\/editor/, { timeout: 15_000 });
    await expect(page.locator("body")).toBeVisible();
  });
});
