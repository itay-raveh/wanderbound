import { mountWithPlugins } from "../helpers";
import NavMapItem from "@/components/editor/nav/NavMapItem.vue";

describe("NavMapItem", () => {
  it("opens step-range editing from a dedicated edit action", async () => {
    const dateRange = ["2024-01-01", "2024-01-03"] as const;
    const wrapper = mountWithPlugins(NavMapItem, {
      props: {
        dateRange,
        rangeIdx: 2,
        active: false,
        color: "#123456",
        formatMapRange: () => "Jan 1 - Jan 3",
      },
    });

    await wrapper.get('button[aria-label="Edit map"]').trigger("click");

    expect(wrapper.text()).toContain("Jan 1 - Jan 3");
    expect(wrapper.emitted("edit")).toEqual([[2, dateRange]]);
  });

  it("keeps the existing delete action", async () => {
    const wrapper = mountWithPlugins(NavMapItem, {
      props: {
        dateRange: ["2024-01-01", "2024-01-03"],
        rangeIdx: 2,
        active: false,
        color: "#123456",
        formatMapRange: () => "Jan 1 - Jan 3",
      },
    });

    await wrapper.get('button[aria-label="Remove map"]').trigger("click");

    expect(wrapper.emitted("delete")).toHaveLength(1);
  });
});
