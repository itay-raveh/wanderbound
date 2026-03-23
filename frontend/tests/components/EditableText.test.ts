import EditableText from "@/components/album/EditableText.vue";
import { mountWithPlugins } from "../helpers";

function mountEditableText(props: Record<string, unknown> = {}) {
  return mountWithPlugins(EditableText, {
    props: { modelValue: "Hello World", ...props },
  });
}

describe("EditableText", () => {
  it("emits update:modelValue on blur with changed text", async () => {
    const wrapper = mountEditableText({ modelValue: "Original" });
    const el = wrapper.find(".editable-text");

    // Simulate focus then modify innerText then blur
    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "Changed";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeTruthy();
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Changed"]);
  });

  it("does not emit update:modelValue on blur when text is unchanged", async () => {
    const wrapper = mountEditableText({ modelValue: "Same" });
    const el = wrapper.find(".editable-text");

    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "Same";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
  });

  it("trims whitespace on commit", async () => {
    const wrapper = mountEditableText({ modelValue: "Original" });
    const el = wrapper.find(".editable-text");

    await el.trigger("focus");
    (el.element as HTMLElement).innerText = "  Trimmed  ";
    await el.trigger("blur");

    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["Trimmed"]);
  });
});
