import { config } from "@vue/test-utils";
import { Quasar } from "quasar";
import { server } from "./mocks/server";

vi.mock("mapbox-gl");

vi.mock("vue3-google-login", () => ({
  default: { install: vi.fn() },
  googleOneTap: vi.fn(),
  GoogleLogin: { name: "GoogleLogin", template: "<div />" },
}));

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

config.global.plugins = [[Quasar, {}]];
