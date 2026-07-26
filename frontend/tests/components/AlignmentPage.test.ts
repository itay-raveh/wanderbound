import AlignmentPage from "@/components/album/AlignmentPage.vue";
import { mountWithPlugins } from "../helpers";

describe("AlignmentPage", () => {
  test("keeps its editor explanation outside the printable artwork", () => {
    const wrapper = mountWithPlugins(AlignmentPage);

    expect(wrapper.get(".alignment-artwork img").attributes("src")).toBe(
      "/topo-contours.svg",
    );
    expect(wrapper.get(".alignment-help").text()).not.toBe("");
    expect(wrapper.get(".page-container").find(".alignment-help").exists()).toBe(
      false,
    );
  });
});
