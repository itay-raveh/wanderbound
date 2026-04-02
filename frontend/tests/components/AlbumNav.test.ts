import { mountWithPlugins, makeStep } from "../helpers";
import AlbumNav from "@/components/editor/AlbumNav.vue";
import { useActiveSection } from "@/composables/useActiveSection";
import { rangeSectionKey } from "@/components/album/albumSections";
import { flushPromises } from "@vue/test-utils";
import type { DateRange } from "@/client";

// Mock useTextMeasure to avoid document.fonts in happy-dom
vi.mock("@/composables/useTextMeasure", () => ({
  measureDescription: (text: string) => {
    if (!text || text.length < 100)
      return { type: "short", mainLines: null, continuationLines: [] };
    if (text.length < 500)
      return { type: "long", mainLines: null, continuationLines: [] };
    return { type: "extra-long", mainLines: null, continuationLines: [[]] };
  },
}));

function nlStep(id: number, name: string) {
  return makeStep({
    id,
    name,
    datetime: `2024-01-0${id}T12:00:00+01:00`,
    timestamp: 1704067200 + (id - 1) * 86400,
    location: { lat: 52.37, lon: 4.89, name, detail: "North Holland", country_code: "nl" },
  });
}

function arStep(id: number, name: string) {
  return makeStep({
    id,
    name,
    datetime: `2024-01-0${id}T12:00:00-03:00`,
    timestamp: 1704067200 + (id - 1) * 86400,
    location: { lat: -34.6, lon: -58.38, name, detail: "Buenos Aires", country_code: "ar" },
  });
}

describe("AlbumNav active section integration", () => {
  afterEach(() => {
    useActiveSection().resetActiveSection();
  });

  function mountNav(steps = [nlStep(1, "Amsterdam"), nlStep(2, "Rotterdam"), arStep(3, "Buenos Aires")]) {
    return mountWithPlugins(AlbumNav, {
      props: {
        steps,
        albumIds: [],
        excludedSteps: [],
        colors: { nl: "#e77c31", ar: "#3b82f6" },
        mapsRanges: [],
      },
    });
  }

  it("expands the correct country group when activeStepId changes", async () => {
    const wrapper = mountNav();
    const { setActive } = useActiveSection();

    // Initially no group is expanded
    await flushPromises();

    // Set the visible step to Buenos Aires (step 3, country "ar")
    setActive(3);
    await flushPromises();

    // The Argentina group should be expanded — find expansion items
    const expansionItems = wrapper.findAllComponents({ name: "QExpansionItem" });
    // There should be 2 groups: nl and ar
    expect(expansionItems).toHaveLength(2);

    // The ar group (index 1) should be open
    const arGroup = expansionItems[1]!;
    expect(arGroup.props("modelValue")).toBe(true);
  });

  it("applies .visible class to the active step nav item", async () => {
    const wrapper = mountNav();
    const { setActive } = useActiveSection();

    await flushPromises();

    setActive(2);
    await flushPromises();

    const navItem = wrapper.find("[data-nav-step='2']");
    expect(navItem.exists()).toBe(true);
    expect(navItem.classes()).toContain("visible");

    // Other steps should not have .visible
    const otherItem = wrapper.find("[data-nav-step='1']");
    expect(otherItem.classes()).not.toContain("visible");
  });

  it("applies .visible class to header sections when activeSectionKey changes", async () => {
    const wrapper = mountNav();
    const { setActive } = useActiveSection();

    await flushPromises();

    setActive("overview");
    await flushPromises();

    const overviewItem = wrapper.find("[data-nav-section='overview']");
    expect(overviewItem.exists()).toBe(true);
    expect(overviewItem.classes()).toContain("visible");
  });

  it("switches expanded group when scrolling to a different country", async () => {
    const wrapper = mountNav();
    const { setActive } = useActiveSection();

    await flushPromises();

    // First scroll to NL step
    setActive(1);
    await flushPromises();

    const expansionItems = wrapper.findAllComponents({ name: "QExpansionItem" });
    expect(expansionItems[0]!.props("modelValue")).toBe(true);

    // Now scroll to AR step
    setActive(3);
    await flushPromises();

    // AR group should now be expanded, NL collapsed
    expect(expansionItems[1]!.props("modelValue")).toBe(true);
    expect(expansionItems[0]!.props("modelValue")).toBe(false);
  });

  it("highlights map entry when activeSectionKey matches its date range", async () => {
    const dateRange: DateRange = ["2024-01-01", "2024-01-31"];
    const steps = [nlStep(1, "Amsterdam"), nlStep(2, "Rotterdam")];

    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        steps,
        albumIds: [],
        excludedSteps: [],
        colors: { nl: "#e77c31" },
        mapsRanges: [dateRange],
      },
    });

    const { setActive } = useActiveSection();
    await flushPromises();

    // Set section key to the map range — this is what AlbumViewer does when a map section is visible
    setActive(rangeSectionKey("map", dateRange));
    await flushPromises();

    const mapEntry = wrapper.find(`[data-nav-section="${rangeSectionKey("map", dateRange)}"]`);
    expect(mapEntry.exists()).toBe(true);
    expect(mapEntry.classes()).toContain("visible");
  });

  it("expands the country group containing the visible map entry", async () => {
    const nlRange: DateRange = ["2024-01-01", "2024-01-02"];
    const arRange: DateRange = ["2024-01-03", "2024-01-04"];
    const steps = [
      nlStep(1, "Amsterdam"),
      arStep(3, "Buenos Aires"),
    ];

    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        steps,
        albumIds: [],
        excludedSteps: [],
        colors: { nl: "#e77c31", ar: "#3b82f6" },
        mapsRanges: [nlRange, arRange],
      },
    });

    const { setActive } = useActiveSection();
    await flushPromises();

    // Scroll to AR map section
    setActive(rangeSectionKey("map", arRange));
    await flushPromises();

    const expansionItems = wrapper.findAllComponents({ name: "QExpansionItem" });
    // AR group (index 1) should be expanded
    expect(expansionItems[1]!.props("modelValue")).toBe(true);
  });
});
