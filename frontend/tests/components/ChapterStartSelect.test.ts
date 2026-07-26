import { mountWithPlugins } from "../helpers";
import ChapterStartSelect from "@/components/editor/nav/ChapterStartSelect.vue";

describe("ChapterStartSelect", () => {
  it("owns the shared row shell used by every step selector", () => {
    const wrapper = mountWithPlugins(ChapterStartSelect, {
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

    const row = wrapper.get(".chapter-start-item");
    expect(row.find(".chapter-start-select").exists()).toBe(true);
  });
});
