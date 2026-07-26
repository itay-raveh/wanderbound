import { mountWithPlugins } from "../helpers";
import StepSelect from "@/components/editor/nav/StepSelect.vue";

describe("StepSelect", () => {
  it("owns the shared row shell used by every step selector", () => {
    const wrapper = mountWithPlugins(StepSelect, {
      props: {
        modelValue: 1,
        options: [
          {
            value: 1,
            label: "Buenos Aires",
            countryCode: "AR",
            countryLabel: "Argentina",
          },
        ],
      },
    });

    const row = wrapper.get(".step-select-item");
    expect(row.find(".step-select").exists()).toBe(true);
  });
});
