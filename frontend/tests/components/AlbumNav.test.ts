import { defineComponent, nextTick, type PropType } from "vue";
import { mountWithPlugins, makeStep } from "../helpers";
import AlbumNav from "@/components/editor/AlbumNav.vue";
import { useActiveSection } from "@/composables/useActiveSection";
import type { CountryVisit } from "@/components/editor/nav/types";
import type { StepRead as Step } from "@/client";

vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({
    formatDateRange: (start: Date, end: Date) =>
      `${start.toISOString()} - ${end.toISOString()}`,
    countryName: (code: string, detail: string) => detail || code,
  }),
}));

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate: vi.fn() }),
}));

const NavCountryGroupStub = defineComponent({
  name: "NavCountryGroup",
  props: {
    group: {
      type: Object as PropType<CountryVisit>,
      required: true,
    },
    open: {
      type: Boolean,
      required: true,
    },
  },
  template:
    '<div class="nav-country-group" :data-group-key="group.key" :data-open="String(open)" />',
});

function makeSteps(count: number): Step[] {
  return Array.from({ length: count }, (_, index) =>
    makeStep({
      id: index + 1,
      name: `Step ${index + 1}`,
      datetime: `2024-01-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z`,
      location: {
        lat: 0,
        lon: 0,
        name: `Place ${index + 1}`,
        detail: `Country ${Math.floor(index / 40)}`,
        country_code: `c${Math.floor(index / 40)}`,
      },
    }),
  );
}

describe("AlbumNav", () => {
  afterEach(() => {
    useActiveSection().resetActiveSection();
    vi.restoreAllMocks();
  });

  it("opens the active step group in a large album", async () => {
    const steps = makeSteps(240);
    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        steps,
        hiddenSteps: [],
        hiddenHeaders: [],
        colors: {},
        mapsRanges: [],
      },
      global: {
        stubs: {
          NavCountryGroup: NavCountryGroupStub,
          NavDateFilter: true,
          NavMapRanges: true,
          QIcon: true,
          QSelect: true,
        },
      },
    });

    await nextTick();
    useActiveSection().setActive(121);
    await nextTick();
    await nextTick();

    expect(wrapper.get('[data-group-key="c3-3"]').attributes("data-open")).toBe(
      "true",
    );
  });
});
