import { mountWithPlugins } from "../helpers";
import EditorHeader from "@/components/editor/EditorHeader.vue";

describe("EditorHeader", () => {
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
