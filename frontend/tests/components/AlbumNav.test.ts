import { defineComponent, nextTick, type PropType } from "vue";
import { mountWithPlugins, makeStep } from "../helpers";
import AlbumNav from "@/components/editor/AlbumNav.vue";
import { useActiveSection } from "@/composables/useActiveSection";
import type { CountryVisit } from "@/components/editor/nav/types";
import type { AlbumChapter, StepRead as Step } from "@/client";
import { mockAlbum, mockMedia } from "../fixtures/mocks";

const mutate = vi.fn();

vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({
    formatDateRange: (start: Date, end: Date) =>
      `${start.toISOString()} - ${end.toISOString()}`,
    countryName: (code: string, detail: string) => detail || code,
  }),
}));

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate }),
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

const QBtnToggleStub = defineComponent({
  name: "QBtnToggle",
  props: {
    modelValue: {
      type: String,
      required: true,
    },
  },
  emits: ["update:modelValue"],
  template: `<button type="button" class="chapter-mode" @click="$emit('update:modelValue', 'chapters')">chapters</button>`,
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
    mutate.mockReset();
    vi.restoreAllMocks();
  });

  it("opens the active step group in a large album", async () => {
    const steps = makeSteps(240);
    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        album: mockAlbum,
        media: mockMedia,
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
        album: mockAlbum,
        media: mockMedia,
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

  it("shows only chapter map ranges in chapter mode", async () => {
    const steps = makeSteps(4);
    const chapters: AlbumChapter[] = [
      {
        id: "chapter-1",
        title: "First chapter",
        subtitle: null,
        step_ids: [1, 2],
        front_cover_photo: "cover.jpg",
        back_cover_photo: "cover.jpg",
      },
    ];
    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        album: { ...mockAlbum, chapters },
        media: mockMedia,
        steps,
        hiddenSteps: [],
        hiddenHeaders: [],
        colors: {},
        mapsRanges: [
          ["2024-01-01", "2024-01-02"],
          ["2024-01-03", "2024-01-04"],
        ],
      },
      global: {
        stubs: {
          NavCountryGroup: NavCountryGroupStub,
          NavDateFilter: true,
          NavMapRanges: true,
          NavChapterGroup: false,
          NavMapItem: {
            props: ["dateRange"],
            template: `<div class="chapter-map" :data-range="dateRange.join('|')" />`,
          },
          NavStepItem: {
            props: ["name"],
            template: `<div class="chapter-step">{{ name }}</div>`,
          },
          QBtnToggle: QBtnToggleStub,
          QIcon: true,
          QSelect: true,
        },
      },
    });

    await wrapper.get(".chapter-mode").trigger("click");
    await nextTick();

    const chapter = wrapper.get('[data-chapter-group="chapter-1"]');
    expect(chapter.find('[data-range="2024-01-01|2024-01-02"]').exists()).toBe(
      true,
    );
    expect(chapter.find('[data-range="2024-01-03|2024-01-04"]').exists()).toBe(
      false,
    );
  });

  it("creates chapters from the nav drawer unassigned group", async () => {
    const steps = [
      makeStep({ id: 1, name: "Buenos Aires" }),
      makeStep({ id: 2, name: "Ushuaia" }),
    ];
    const wrapper = mountWithPlugins(AlbumNav, {
      props: {
        album: { ...mockAlbum, chapters: [] },
        media: mockMedia,
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
          NavMapItem: true,
          NavStepItem: true,
          QBtnToggle: QBtnToggleStub,
          QIcon: true,
          QSelect: true,
        },
      },
    });

    await wrapper.get(".chapter-mode").trigger("click");
    await wrapper.get(".chapter-action").trigger("click");

    expect(mutate).toHaveBeenCalledWith({
      chapters: [
        expect.objectContaining({
          id: "chapter-1",
          step_ids: [1, 2],
        }),
      ],
    });
  });
});
