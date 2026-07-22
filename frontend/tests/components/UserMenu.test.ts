import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { createMemoryHistory, createRouter } from "vue-router";
import { client } from "@/client/client.gen";
import i18n from "@/i18n";
import UserMenu from "@/components/editor/UserMenu.vue";
import { mockUser } from "../fixtures/mocks";
import { BASE } from "../mocks/handlers";
import { server } from "../mocks/server";

client.setConfig({ baseUrl: "http://localhost:8000" });

describe("UserMenu", () => {
  it("opens the upload page with explicit reupload intent", async () => {
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
});
