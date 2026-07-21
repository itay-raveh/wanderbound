import { config, enableAutoUnmount } from "@vue/test-utils";
import { Quasar } from "quasar";
import { server } from "./mocks/server";

vi.mock("mapbox-gl");

vi.mock("vue3-google-login", () => ({
  default: { install: vi.fn() },
  googleOneTap: vi.fn(),
  GoogleLogin: { name: "GoogleLogin", template: "<div />" },
}));

vi.mock("@/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/config")>();
  const settings = new Proxy(
    {
      ENVIRONMENT: "local",
      MAX_UPLOAD_SIZE_BYTES: 4 * 1024 ** 3,
    },
    { get: (target, key) => Reflect.get(target, key) ?? null },
  );
  return { ...actual, getPublicSettings: () => settings };
});

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
enableAutoUnmount(afterEach);
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

config.global.plugins = [[Quasar, {}]];
