import { mountWithPlugins } from "../helpers";
import EditorHeader from "@/components/editor/EditorHeader.vue";

describe("EditorHeader", () => {
  it("renders persistent content above the toolbar row", () => {
    const wrapper = mountWithPlugins(EditorHeader, {
      slots: {
        banner: '<div class="demo-banner">Demo banner</div>',
        default: '<div class="album-toolbar">Album toolbar</div>',
      },
      global: {
        stubs: {
          QHeader: { template: "<header><slot /></header>" },
          UserMenu: true,
        },
      },
    });

    const header = wrapper.get("header");
    expect(header.get(".demo-banner").text()).toBe("Demo banner");
    expect(header.get(".editor-header__toolbar .album-toolbar").text()).toBe(
      "Album toolbar",
    );
    expect(header.element.children[0]?.classList.contains("demo-banner")).toBe(
      true,
    );
  });

  it("keeps rail controls out of the global header", () => {
    const wrapper = mountWithPlugins(EditorHeader, {
      global: {
        stubs: {
          QHeader: { template: "<header><slot /></header>" },
          UserMenu: true,
        },
      },
    });

    expect(wrapper.find('[aria-controls="editor-navigation"]').exists()).toBe(
      false,
    );
    expect(wrapper.find('[aria-controls="editor-inspector"]').exists()).toBe(
      false,
    );
  });
});
