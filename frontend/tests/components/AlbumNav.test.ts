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
    `<div class="nav-country-group" :data-group-key="group.key" :data-open="String(open)">
      <div
        v-for="entry in group.entries"
        :key="entry.type === 'step' ? entry.item.id : entry.key"
        :data-nav-step="entry.type === 'step' ? entry.item.id : undefined"
        :data-nav-section="entry.type === 'map' ? entry.key : undefined"
      />
    </div>`,
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

  it("does not scroll the nav list while the viewer is programmatically scrolling", async () => {
    const scrollIntoView = vi
      .spyOn(Element.prototype, "scrollIntoView")
      .mockImplementation(() => {});
    const steps = makeSteps(80);
    mountWithPlugins(AlbumNav, {
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
    const activeSection = useActiveSection();
    activeSection.programmaticScrolling.value = true;
    activeSection.setActive(41);
    await nextTick();
    await nextTick();

    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
