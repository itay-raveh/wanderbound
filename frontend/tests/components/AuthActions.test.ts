import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import AuthActions from "@/components/landing/AuthActions.vue";
import i18n from "@/i18n";

function mountAuthActions(localLoginEnabled: boolean) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "landing", component: { template: "<div />" } },
      { path: "/upload", name: "upload", component: { template: "<div />" } },
    ],
  });
  return mount(AuthActions, {
    props: {
      authenticated: false,
      demoLoading: false,
      localLoginEnabled,
    },
    global: {
      plugins: [i18n, router],
      stubs: { LoginButtons: { template: '<div data-test="providers" />' } },
    },
  });
}

it("shows ZIP login instead of provider login in local mode", () => {
  const wrapper = mountAuthActions(true);

  expect(wrapper.get('[data-test="local-login"]').text()).toContain(
    "Log in with Polarsteps ZIP",
  );
  expect(wrapper.find('[data-test="providers"]').exists()).toBe(false);
});

it("shows provider login instead of ZIP login outside local mode", () => {
  const wrapper = mountAuthActions(false);

  expect(wrapper.find('[data-test="providers"]').exists()).toBe(true);
  expect(wrapper.find('[data-test="local-login"]').exists()).toBe(false);
});
