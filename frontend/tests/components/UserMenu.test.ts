import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { createMemoryHistory, createRouter } from "vue-router";
import { client } from "@/client/client.gen";
import i18n from "@/i18n";
import UserMenu from "@/components/editor/UserMenu.vue";

const providerSettings = vi.hoisted(() => ({
  GOOGLE_CLIENT_ID: "configured",
  MICROSOFT_CLIENT_ID: "",
}));

vi.mock("@/config", () => ({
  getSettings: () => providerSettings,
  isLocalLoginEnabled: (settings: typeof providerSettings) =>
    !settings.GOOGLE_CLIENT_ID && !settings.MICROSOFT_CLIENT_ID,
}));

client.setConfig({ baseUrl: "http://localhost:8000" });

describe("UserMenu", () => {
  beforeEach(() => {
    providerSettings.GOOGLE_CLIENT_ID = "configured";
    providerSettings.MICROSOFT_CLIENT_ID = "";
  });

  async function mountMenu() {
    const history = createMemoryHistory();
    const router = createRouter({
      history,
      routes: [
        { path: "/editor", name: "editor", component: { template: "<div />" } },
        { path: "/upload", name: "upload", component: { template: "<div />" } },
      ],
    });
    await router.push({ name: "editor" });
    await router.isReady();

    const wrapper = mount(UserMenu, {
      attachTo: document.body,
      global: {
        plugins: [
          createPinia(),
          PiniaColada,
          i18n,
          router,
        ],
      },
    });
    await flushPromises();

    return { history, router, wrapper };
  }

  it("opens the upload page with explicit reupload intent", async () => {
    const { history, router, wrapper } = await mountMenu();

    await wrapper.get(".settings-trigger").trigger("click");
    await flushPromises();
    const reupload = [...document.body.querySelectorAll("button")].find(
      (button) => button.textContent?.includes("Re-upload data"),
    );
    expect(reupload).toBeDefined();

    reupload!.click();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("upload");
    expect(history.state.reupload).toBe(true);
  });

  it("hides sign out but keeps account actions in local mode", async () => {
    providerSettings.GOOGLE_CLIENT_ID = "";
    const { wrapper } = await mountMenu();

    await wrapper.get(".settings-trigger").trigger("click");
    await flushPromises();
    const account = document.body.querySelector<HTMLDetailsElement>(
      ".account-details",
    );
    expect(account).not.toBeNull();
    account!.open = true;
    await wrapper.vm.$nextTick();

    const text = account!.textContent ?? "";
    expect(text).toContain("Re-upload data");
    expect(text).toContain("Export my data");
    expect(text).toContain("Delete all data");
    expect(document.body.querySelector(".settings-card")?.textContent).not.toContain(
      "Sign out",
    );
  });
});
