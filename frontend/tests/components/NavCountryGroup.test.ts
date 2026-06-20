import { defineComponent, type PropType } from "vue";
import { mountWithPlugins } from "../helpers";
import NavCountryGroup from "@/components/editor/nav/NavCountryGroup.vue";
import type { CountryVisit, GroupEntry } from "@/components/editor/nav/types";
import type { StepRead as Step } from "@/client";

const ExpansionItemStub = defineComponent({
  name: "QExpansionItem",
  props: {
    modelValue: { type: Boolean, default: false },
  },
  emits: ["update:modelValue"],
  template:
    '<section class="country-group"><button type="button" @click="$emit(\'update:modelValue\', !modelValue)"><slot name="header" /></button><slot v-if="modelValue" /></section>',
});

const VirtualScrollStub = defineComponent({
  name: "QVirtualScroll",
  props: {
    items: {
      type: Array as PropType<GroupEntry[]>,
      required: true,
    },
    virtualScrollSliceSize: {
      type: Number,
      default: 20,
    },
  },
  setup(_props, { expose }) {
    const scrollTo = vi.fn();
    expose({ scrollTo });
    return { scrollTo };
  },
  template:
    '<div class="virtual-scroll-stub"><template v-for="(item, index) in items.slice(0, virtualScrollSliceSize)" :key="index"><slot :item="item" :index="index" /></template></div>',
});

const NavStepItemStub = defineComponent({
  name: "NavStepItem",
  props: {
    name: { type: String, required: true },
  },
  emits: ["click", "toggle"],
  template:
    '<div class="nav-step-item" role="button" @click="$emit(\'click\')">{{ name }}</div>',
});

function makeGroup(count: number): CountryVisit {
  const entries = Array.from({ length: count }, (_, index): GroupEntry => {
    const id = index + 1;
    return {
      type: "step",
      item: {
        id,
        name: `Step ${id}`,
        country: "nl",
        color: "#e77c31",
        date: new Date("2024-01-01T00:00:00Z"),
        thumb: null,
        detail: "Netherlands",
      },
    };
  });
  return {
    key: "nl-0",
    code: "nl",
    name: "Netherlands",
    color: "#e77c31",
    entries,
    stepIds: entries.map((entry) => entry.item.id),
    entryIndexByStepId: new Map(
      entries.map((entry, index) => [entry.item.id, index]),
    ),
    dateRange: "Jan 1 - Jan 1",
  };
}

describe("NavCountryGroup", () => {
  it("does not mount every step row for a large open group", () => {
    const group = makeGroup(240);

    const wrapper = mountWithPlugins(NavCountryGroup, {
      props: {
        group,
        open: true,
        activeStepId: null,
        activeSectionKey: null,
        hiddenSet: new Set<number>(),
        steps: [] as Step[],
        colors: {},
        formatMapRange: () => "",
      },
      global: {
        stubs: {
          NavMapItem: true,
          NavStepItem: NavStepItemStub,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QItemSection: { template: "<div><slot /></div>" },
          QVirtualScroll: VirtualScrollStub,
        },
      },
    });

    expect(wrapper.findAll(".nav-step-item").length).toBeLessThan(
      group.entries.length,
    );
  });

  it("scrolls the active virtual row into view", async () => {
    const group = makeGroup(240);

    const wrapper = mountWithPlugins(NavCountryGroup, {
      props: {
        group,
        open: true,
        activeStepId: null,
        activeSectionKey: null,
        hiddenSet: new Set<number>(),
        steps: [] as Step[],
        colors: {},
        formatMapRange: () => "",
      },
      global: {
        stubs: {
          NavMapItem: true,
          NavStepItem: NavStepItemStub,
          QExpansionItem: ExpansionItemStub,
          QIcon: true,
          QItemSection: { template: "<div><slot /></div>" },
          QVirtualScroll: VirtualScrollStub,
        },
      },
    });

    await wrapper.setProps({ activeStepId: 200 });

    expect(
      wrapper.getComponent(VirtualScrollStub).vm.scrollTo,
    ).toHaveBeenCalledWith(199);
  });
});
