import type { Settings } from "@/config";

const api = vi.hoisted(() => ({ publicConfig: vi.fn() }));

vi.mock("@/client", () => api);
vi.unmock("@/config");

const publicSettings = {
  PUBLIC_URL: "https://wanderbound.example",
} as Settings;

beforeEach(() => {
  vi.resetModules();
  api.publicConfig.mockReset();
});

it("loads public settings once before exposing them", async () => {
  api.publicConfig.mockResolvedValue({ data: publicSettings });
  const { getSettings, loadSettings } = await import("@/config");

  const [first, second] = await Promise.all([
    loadSettings(),
    loadSettings(),
  ]);

  expect(api.publicConfig).toHaveBeenCalledOnce();
  expect(first).toMatchObject(publicSettings);
  expect(second).toBe(first);
  expect(getSettings()).toBe(first);
});

it("rejects access before startup configuration has loaded", async () => {
  const { getSettings } = await import("@/config");

  expect(() => getSettings()).toThrow("Public settings are not loaded");
});

it("rejects an invalid startup configuration response", async () => {
  api.publicConfig.mockResolvedValue({ data: { PUBLIC_URL: 42 } });
  const { loadSettings } = await import("@/config");

  await expect(loadSettings()).rejects.toThrow();
});
