import { mountWithPlugins } from "../helpers";
import EditorRailControl from "@/components/editor/EditorRailControl.vue";

const navigationProps = {
  side: "left" as const,
  open: true,
  title: "Album",
  controls: "editor-navigation",
  showLabel: "Show navigation",
  hideLabel: "Hide navigation",
};

describe("EditorRailControl", () => {
  it("renders an open rail header with its close action on the inner edge", async () => {
    const wrapper = mountWithPlugins(EditorRailControl, {
      props: navigationProps,
    });

    const header = wrapper.get(".editor-rail-control--open");
    const button = wrapper.get('[aria-controls="editor-navigation"]');

    expect(header.classes()).toContain("editor-rail-control--left");
    expect(header.text()).toContain("Album");
    expect(button.attributes("aria-expanded")).toBe("true");
    expect(button.attributes("aria-label")).toBe("Hide navigation");

    await button.trigger("click");

    expect(wrapper.emitted("toggle")).toHaveLength(1);
  });

  it("renders only an attached edge action while the rail is closed", async () => {
    const wrapper = mountWithPlugins(EditorRailControl, {
      props: {
        ...navigationProps,
        side: "right",
        open: false,
        title: "Inspector",
        controls: "editor-inspector",
        showLabel: "Show inspector",
        hideLabel: "Hide inspector",
      },
    });

    const edge = wrapper.get(".editor-rail-control--edge");

    expect(wrapper.find(".editor-rail-control--open").exists()).toBe(false);
    expect(edge.classes()).toContain("editor-rail-control--right");
    expect(edge.attributes("aria-expanded")).toBe("false");
    expect(edge.attributes("aria-label")).toBe("Show inspector");

    await edge.trigger("click");

    expect(wrapper.emitted("toggle")).toHaveLength(1);
  });
});
