import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { createMemoryHistory, createRouter } from "vue-router";
import { http, HttpResponse } from "msw";
import { client } from "@/client/client.gen";
import i18n from "@/i18n";
import UserMenu from "@/components/editor/UserMenu.vue";
import { mockUser } from "../fixtures/mocks";
import { BASE } from "../mocks/handlers";
import { server } from "../mocks/server";

client.setConfig({ baseUrl: "http://localhost:8000" });

describe("UserMenu", () => {
  it("shows Molly's profile image in demo mode", async () => {
    server.use(
      http.get(`${BASE}/users`, () =>
        HttpResponse.json({
          ...mockUser,
          first_name: "Molly",
          is_demo: true,
          profile_image_url: "/demo/molly-avatar.webp",
        }),
      ),
    );
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/editor", name: "editor", component: { template: "<div />" } },
      ],
    });
    await router.push({ name: "editor" });
    await router.isReady();

    const wrapper = mount(UserMenu, {
      global: {
        plugins: [createPinia(), PiniaColada, i18n, router],
      },
    });
    await flushPromises();

    const avatar = wrapper.get(".trigger-avatar img");
    expect(avatar.attributes("src")).toBe("/demo/molly-avatar.webp");
    expect(avatar.attributes("alt")).toBe("Molly");
  });

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
