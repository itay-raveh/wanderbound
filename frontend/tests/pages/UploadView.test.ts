import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { http, HttpResponse } from "msw";
import { createMemoryHistory, createRouter } from "vue-router";
import { processUser } from "@/client";
import { client } from "@/client/client.gen";
import i18n from "@/i18n";
import UploadView from "@/pages/UploadView.vue";
import { mockAuthStateAuthenticated, mockUser } from "../fixtures/mocks";
import { BASE } from "../mocks/handlers";
import { server } from "../mocks/server";

client.setConfig({ baseUrl: "http://localhost:8000" });

vi.mock("@mapbox/mapbox-gl-supported", () => ({
  isSupported: () => true,
  notSupportedReason: () => "",
}));

vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

vi.mock("@/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/client")>()),
  processUser: vi.fn(),
}));

const mockedProcessUser = vi.mocked(processUser);

async function* completedStream() {
  await Promise.resolve();
}

async function mountUploadView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/upload", name: "upload", component: UploadView },
      { path: "/editor", name: "editor", component: { template: "<div />" } },
    ],
  });
  await router.push({ name: "upload" });
  await router.isReady();

  return mount(UploadView, {
    global: {
      plugins: [
        createPinia(),
        PiniaColada,
        i18n,
        router,
      ],
      stubs: {
        QPage: { template: "<main><slot /></main>" },
      },
    },
  });
}

describe("UploadView", () => {
  beforeEach(() => {
    mockedProcessUser.mockResolvedValue({
      stream: completedStream(),
    } as Awaited<ReturnType<typeof processUser>>);
    window.history.replaceState({}, "");
  });

  it("honors explicit reupload intent even when cached processing is incomplete", async () => {
    const incompleteUser = { ...mockUser, is_processed: false };
    server.use(
      http.get(`${BASE}/auth/state`, () =>
        HttpResponse.json({
          ...mockAuthStateAuthenticated,
          user: incompleteUser,
        }),
      ),
      http.get(`${BASE}/users`, () => HttpResponse.json(incompleteUser)),
    );
    window.history.replaceState({ reupload: true }, "");

    const wrapper = await mountUploadView();
    await flushPromises();

    expect(wrapper.find('input[type="file"]').exists()).toBe(true);
    expect(mockedProcessUser).not.toHaveBeenCalled();
  });

  it("refreshes the user after processing completes", async () => {
    let userRequests = 0;
    const incompleteUser = { ...mockUser, is_processed: false };
    server.use(
      http.get(`${BASE}/auth/state`, () =>
        HttpResponse.json({
          ...mockAuthStateAuthenticated,
          user: incompleteUser,
        }),
      ),
      http.get(`${BASE}/users`, () => {
        userRequests += 1;
        return HttpResponse.json({
          ...mockUser,
          is_processed: userRequests > 1,
        });
      }),
    );

    const wrapper = await mountUploadView();

    await vi.waitFor(() => {
      expect(userRequests).toBe(2);
      expect(wrapper.find('input[type="file"]').exists()).toBe(true);
    });
  });
});
