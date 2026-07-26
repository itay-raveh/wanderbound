import { defineComponent, nextTick } from "vue";
import { mountWithPlugins, makeStep } from "../helpers";
import MapRangeDialog from "@/components/editor/nav/MapRangeDialog.vue";
import ChapterStartSelect from "@/components/editor/nav/ChapterStartSelect.vue";
import PromptDialog from "@/components/ui/PromptDialog.vue";

vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => {
    const localDate = (date: Date) =>
      [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
      ].join("-");
    return {
      countryName: (code: string, detail: string) => detail || code,
      formatDate: localDate,
      formatDateRange: (start: Date, end: Date) =>
        `${localDate(start)} – ${localDate(end)}`,
    };
  },
}));

const DialogStub = defineComponent({
  props: { modelValue: Boolean },
  emits: ["update:modelValue"],
  template: "<div v-if=\"modelValue\"><slot /></div>",
});

const ButtonStub = defineComponent({
  props: { disable: Boolean },
  template: "<button :disabled=\"disable\"><slot /></button>",
});

function mountDialog() {
  const steps = [
    makeStep({ id: 1, name: "Buenos Aires", datetime: "2024-01-01T00:00:00Z" }),
    makeStep({ id: 2, name: "Ushuaia", datetime: "2024-01-02T00:00:00Z" }),
    makeStep({ id: 3, name: "Santiago", datetime: "2024-01-03T00:00:00Z" }),
  ];
  return mountWithPlugins(MapRangeDialog, {
    props: {
      modelValue: false,
      steps,
      dateRange: ["2024-01-01", "2024-01-03"],
    },
    global: {
      stubs: {
        QDialog: DialogStub,
        QCard: { template: "<div><slot /></div>" },
        QBtn: ButtonStub,
      },
    },
  });
}

describe("MapRangeDialog", () => {
  it("uses the shared prompt shell and chapter step selectors", async () => {
    const wrapper = mountDialog();

    await wrapper.setProps({ modelValue: true });
    await nextTick();

    expect(wrapper.findComponent(PromptDialog).exists()).toBe(true);
    expect(wrapper.findAllComponents(ChapterStartSelect)).toHaveLength(2);
  });

  it("uses step dropdowns and prevents an ending step before the start", async () => {
    const wrapper = mountDialog();

    await wrapper.setProps({ modelValue: true });
    await nextTick();

    const selects = wrapper.findAllComponents(ChapterStartSelect);
    expect(selects[0].props("modelValue")).toBe(1);
    expect(selects[1].props("modelValue")).toBe(3);

    selects[0].vm.$emit("update:modelValue", 2);
    await nextTick();

    expect(
      (selects[1].props("options") as { value: number }[]).map(
        (option) => option.value,
      ),
    ).toEqual([2, 3]);
  });

  it("saves the selected step dates as a map range", async () => {
    const wrapper = mountDialog();
    await wrapper.setProps({ modelValue: true });
    await nextTick();

    const selects = wrapper.findAllComponents(ChapterStartSelect);
    selects[0].vm.$emit("update:modelValue", 2);
    selects[1].vm.$emit("update:modelValue", 3);
    await nextTick();
    await wrapper.get(".confirm-btn").trigger("click");

    expect(wrapper.emitted("save")).toEqual([
      [["2024-01-02", "2024-01-03"]],
    ]);
  });

  it("uses chapter-style options and summarizes the selected range", async () => {
    const wrapper = mountDialog();
    await wrapper.setProps({ modelValue: true });
    await nextTick();

    const selects = wrapper.findAllComponents(ChapterStartSelect);
    expect(selects[0].props("options")).toMatchObject([
      { label: "Buenos Aires" },
      { label: "Ushuaia" },
      { label: "Santiago" },
    ]);
    expect(
      (selects[0].props("options") as Record<string, unknown>[]).every(
        (option) => !("detail" in option),
      ),
    ).toBe(true);
    expect(wrapper.get(".map-range-summary").text()).toContain(
      "2024-01-01 – 2024-01-03",
    );
    expect(wrapper.get(".map-range-summary").text()).toContain("3 steps");
  });
});
