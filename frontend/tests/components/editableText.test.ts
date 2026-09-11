import { mount } from "@vue/test-utils";
import EditableText from "@/components/album/EditableText.vue";

describe("text editing", () => {
  test("preserves a description draft when its page rerenders", async () => {
    const wrapper = mount(EditableText, {
      props: { modelValue: "", multiline: true },
    });
    await wrapper.get('[role="button"]').trigger("click");
    await wrapper.get("textarea").setValue("New description");
    await wrapper.setProps({
      page: { text: "", offset: 0, lineIndex: 0, direction: "ltr" },
    });
    expect(wrapper.get("textarea").element.value).toBe("New description");
    await wrapper.get("textarea").trigger("blur");
    expect(wrapper.emitted("update:modelValue")).toEqual([
      ["New description"],
    ]);
  });

  test.each([false, true])(
    "saves pending edits but not canceled edits on unmount (multiline: %s)",
    async (multiline) => {
      for (const cancel of [false, true]) {
        const wrapper = mount(EditableText, {
          props: { modelValue: "Original", multiline },
        });
        if (multiline) {
          await wrapper.get('[role="button"]').trigger("click");
          await wrapper.get("textarea").setValue("Edited text");
        } else {
          const textbox = wrapper.get<HTMLElement>('[role="textbox"]');
          await textbox.trigger("focus");
          textbox.element.innerText = "Edited text";
        }
        if (cancel) {
          await wrapper
            .get(multiline ? "textarea" : '[role="textbox"]')
            .trigger("keydown", { key: "Escape" });
        }
        wrapper.unmount();
        expect(wrapper.emitted("update:modelValue")).toEqual(
          cancel ? undefined : [["Edited text"]],
        );
      }
    },
  );
});
