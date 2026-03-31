import { mountWithPlugins, makeStep } from "../helpers";
import InspectorDrawer from "@/components/editor/InspectorDrawer.vue";
import { useActiveSection } from "@/composables/useActiveSection";
import { computed, ref } from "vue";
import type { Step } from "@/client";
import { defaultAlbum, defaultMedia } from "../mocks/handlers";

// Mock usePhotoFocus — depends on module-level state not available in test
vi.mock("@/composables/usePhotoFocus", () => ({
  usePhotoFocus: () => ({
    focusedPhotoId: ref(null),
    focus: vi.fn(),
    blur: vi.fn(),
    setStepOrder: vi.fn(),
  }),
  STEP_ID_KEY: Symbol("step-id"),
}));

describe("InspectorDrawer context routing", () => {
  it("shows inspector-panel for cover section", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum as never,
        media: defaultMedia as never,
        sectionKey: "cover-front",
      },
    });

    expect(wrapper.find(".inspector-panel").exists()).toBe(true);
  });

  it("shows inspector-panel for map section", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum as never,
        media: defaultMedia as never,
        sectionKey: "full-map",
      },
    });

    expect(wrapper.find(".inspector-panel").exists()).toBe(true);
  });

  it("shows empty inspector-panel when no step or sectionKey", () => {
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum as never,
        media: defaultMedia as never,
      },
    });

    expect(wrapper.find(".inspector-panel").exists()).toBe(true);
  });
});

describe("InspectorDrawer with step (UnusedDrawer rendering)", () => {
  it("renders UnusedDrawer without useAlbum crash when step is provided", () => {
    const step = makeStep({
      id: 1,
      name: "Buenos Aires",
      unused: ["photo1.jpg", "photo2.jpg"],
    });

    // This would throw "useAlbum() called outside of AlbumViewer" before
    // provideAlbum was added to InspectorDrawer.
    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum as never,
        media: defaultMedia as never,
        step,
      },
    });

    // UnusedDrawer should render (not the inspector-panel)
    expect(wrapper.find(".unused-drawer").exists()).toBe(true);
    expect(wrapper.find(".inspector-panel").exists()).toBe(false);
  });

  it("shows correct unused photo count", () => {
    const step = makeStep({
      id: 1,
      name: "Test Step",
      unused: ["a.jpg", "b.jpg", "c.jpg"],
    });

    const wrapper = mountWithPlugins(InspectorDrawer, {
      props: {
        album: defaultAlbum as never,
        media: defaultMedia as never,
        step,
      },
    });

    expect(wrapper.find(".text-faint").text()).toBe("3");
  });
});

describe("activeStep derivation from active section", () => {
  afterEach(() => {
    useActiveSection().resetActiveSection();
  });

  it("finds the matching step when activeStepId changes", () => {
    const { setActive, activeStepId } = useActiveSection();

    const steps = ref([
      makeStep({ id: 1, name: "Amsterdam" }),
      makeStep({ id: 2, name: "Rotterdam" }),
      makeStep({ id: 3, name: "Buenos Aires" }),
    ]);

    // Same logic as EditorView.vue line 55-58
    const activeStep = computed<Step | undefined>(() =>
      activeStepId.value != null
        ? steps.value.find((s) => s.id === activeStepId.value)
        : undefined,
    );

    expect(activeStep.value).toBeUndefined();

    setActive(2);
    expect(activeStep.value).toBeDefined();
    expect(activeStep.value!.name).toBe("Rotterdam");

    setActive("overview");
    expect(activeStep.value).toBeUndefined();

    setActive(3);
    expect(activeStep.value!.name).toBe("Buenos Aires");

    setActive(null);
    expect(activeStep.value).toBeUndefined();
  });
});
