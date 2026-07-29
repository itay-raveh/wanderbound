import { config, enableAutoUnmount } from "@vue/test-utils";
import { Quasar } from "quasar";

vi.mock("mapbox-gl");

vi.mock("vue3-google-login", () => ({
  default: { install: vi.fn() },
  googleOneTap: vi.fn(),
  GoogleLogin: { name: "GoogleLogin", template: "<div />" },
}));

vi.mock("@/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/config")>();
  const { zPublicSettings } = await import("@/client/zod.gen");
  const settings = new Proxy(
    zPublicSettings.parse({}),
    { get: (target, key) => Reflect.get(target, key) ?? null },
  );
  return { ...actual, getSettings: () => settings };
});

enableAutoUnmount(afterEach);

config.global.plugins = [[Quasar, {}]];
