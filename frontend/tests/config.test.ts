import type { RuntimeSettings } from "@/config";

const api = vi.hoisted(() => ({ publicConfig: vi.fn() }));

vi.mock("@/client", () => api);
vi.unmock("@/config");

const publicSettings = {
  PUBLIC_URL: "https://wanderbound.example",
} as RuntimeSettings;

beforeEach(() => {
  vi.resetModules();
  api.publicConfig.mockReset();
});

it("loads public settings once before exposing them", async () => {
  api.publicConfig.mockResolvedValue({ data: publicSettings });
  const { getPublicSettings, loadPublicSettings } = await import("@/config");

  const [first, second] = await Promise.all([
    loadPublicSettings(),
    loadPublicSettings(),
  ]);

  expect(api.publicConfig).toHaveBeenCalledOnce();
  expect(first).toMatchObject(publicSettings);
  expect(second).toBe(first);
  expect(getPublicSettings()).toBe(first);
});

it("rejects access before startup configuration has loaded", async () => {
  const { getPublicSettings } = await import("@/config");

  expect(() => getPublicSettings()).toThrow("Public settings are not loaded");
});

it("rejects an invalid startup configuration response", async () => {
  api.publicConfig.mockResolvedValue({ data: { PUBLIC_URL: 42 } });
  const { loadPublicSettings } = await import("@/config");

  await expect(loadPublicSettings()).rejects.toThrow();
});
